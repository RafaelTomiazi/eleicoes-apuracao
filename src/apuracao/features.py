"""Indicadores históricos do IBGE com publicação anterior às eleições alvo."""

from __future__ import annotations

import re
import hashlib
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

import polars as pl

from apuracao.download import ROOT, download, write_json

POP_URL = "https://ftp.ibge.gov.br/Estimativas_de_Populacao/Estimativas_2021/estimativa_dou_2021.ods"
GDP_URL = "https://ftp.ibge.gov.br/Pib_Municipios/2019/base/base_de_dados_2010_2019_txt.zip"
FEATURES = ["ibge_pop_2021", "ibge_pib_per_capita_2019"]
PUBLISHED = date(2021, 12, 17)


def normalized_name(value: str) -> str:
    """Remove apenas acentos, espaços e pontuação para correspondência exata."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", value.upper()) if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", plain)


def population_2021(path: Path) -> pl.DataFrame:
    """Lê a planilha municipal da edição original ODS de agosto de 2021."""
    ns = {"t": "urn:oasis:names:tc:opendocument:xmlns:table:1.0"}
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    records = []
    for table in root.findall(".//t:table", ns):
        if normalized_name(table.get("{"+ns["t"]+"}name", "")) != "MUNICIPIOS":
            continue
        for row in table.findall("t:table-row", ns):
            cells = []
            for cell in row:
                repeat = int(cell.get("{"+ns["t"]+"}number-columns-repeated", "1"))
                cells.extend(["".join(cell.itertext()).strip()] * min(repeat, 6))
                if len(cells) >= 5:
                    break
            if len(cells) < 5 or not re.fullmatch(r"[A-Z]{2}", cells[0]) or not cells[1].isdigit():
                continue
            amount = re.match(r"[\d.]+", cells[4])
            if not amount:
                raise ValueError(f"População não interpretada: {cells}")
            records.append({"uf": cells[0], "cod_ibge": cells[1].zfill(2)+cells[2].zfill(5),
                            "_nome": normalized_name(cells[3]), "ibge_pop_2021": float(amount[0].replace(".", ""))})
    if len(records) != 5570:
        raise ValueError(f"Esperados 5570 municípios na edição 2021, encontrados {len(records)}")
    return pl.DataFrame(records)


def gdp_2019(path: Path) -> pl.DataFrame:
    """Lê as posições do layout oficial da edição de PIB publicada em 2021."""
    records = []
    with zipfile.ZipFile(path) as archive:
        name = next(name for name in archive.namelist() if name.lower().endswith(".txt"))
        with archive.open(name) as source:
            for binary in source:
                line = binary.decode("cp1252")
                if line[:4] != "2019":
                    continue
                records.append({"cod_ibge": line[46:53], "ibge_pib_per_capita_2019": float(line[952:970])})
    if len(records) != 5570:
        raise ValueError(f"Esperados 5570 municípios no PIB 2019: {len(records)}")
    return pl.DataFrame(records)


def build_indicators(root: Path = ROOT) -> None:
    """Gera indicadores sem usar a tabela TSE–IBGE criada depois do backtest."""
    raw = root / "data" / "raw" / "ibge_historico"
    pop_path = download(POP_URL, raw / "estimativa_dou_2021.ods")
    gdp_path = download(GDP_URL, raw / "base_de_dados_2010_2019_txt.zip")
    # Identidades das edições históricas inspecionadas em FONTES_MODELOS.md.
    for path,expected in ((pop_path,"57746ed3f495f1f3111ed4ed33ee59d6e9ddd4f7023c25434fc79cd1e5b6a8bb"),
                          (gdp_path,"11e50dfb372acfa030ebfa78445a299a371838710925bcdd5bbf4ae931462da2")):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError(f"Edição histórica alterada: {path.name}; revisar a vintagem")
    population = population_2021(pop_path)
    gdp = gdp_2019(gdp_path)
    if population.select("uf", "_nome").is_duplicated().any():
        raise ValueError("Correspondência municipal normalizada ambígua")
    historical = population.join(gdp, on="cod_ibge", how="left", validate="1:1")
    reports = []
    for year in (2022, 2026):
        municipalities = (pl.read_parquet(root / "data" / "processed" / f"pareado_{year}.parquet",
                                        columns=["uf", "cod_municipio", "nome_municipio"])
                          .unique().with_columns(pl.col("nome_municipio").map_elements(normalized_name, return_dtype=pl.String).alias("_nome")))
        if municipalities.select("uf", "cod_municipio").is_duplicated().any():
            raise ValueError("Nome municipal divergente para a mesma chave TSE")
        result = (municipalities.join(historical, on=["uf", "_nome"], how="left", validate="m:1")
                  .select("uf", "cod_municipio", "cod_ibge", *FEATURES)
                  .with_columns(pl.lit(PUBLISHED).alias("ibge_publicado_em"))
                  .sort("uf","cod_municipio"))
        result.write_parquet(root / "data" / "processed" / f"indicadores_{year}.parquet", compression="zstd")
        reports.append({"ano": year, "municipios_tse": result.height,
                        "municipios_sem_indicador": result.filter(pl.col("ibge_pop_2021").is_null()).height,
                        "brasileiros_sem_indicador": result.filter((pl.col("uf")!="ZZ") & pl.col("ibge_pop_2021").is_null()).height,
                        "faltantes":result.filter(pl.col("ibge_pop_2021").is_null()).select("uf","cod_municipio").to_dicts(),
                        "publicado_ate": str(PUBLISHED), "fontes": [POP_URL, GDP_URL]})
    write_json(root / "docs" / "INDICADORES_MODELOS.json", reports)
    print([{key:value for key,value in report.items() if key!="faltantes"} for report in reports], flush=True)


if __name__ == "__main__":
    build_indicators()
