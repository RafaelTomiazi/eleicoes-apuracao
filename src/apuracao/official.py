"""Fontes de totalização do TSE independentes dos arquivos BWEB."""

from pathlib import Path
from typing import Any
import shutil
import tempfile
import zipfile

import duckdb

from apuracao.download import CATALOG, ROOT, download, inspect_zip, read_json, write_json


def fetch_official(year: int, root: Path = ROOT) -> dict[str, Any]:
    """Baixa votação nominal e detalhe por município/zona do catálogo oficial."""
    folder = root / "data" / "raw" / "oficial" / str(year)
    catalog_url = f"{CATALOG}?id=resultados-{year}"
    catalog = read_json(download(catalog_url, folder / "catalogo.json", json_response=True))
    if not catalog.get("success"):
        raise ValueError(f"Catálogo inválido: {catalog_url}")
    sources = {}
    for kind in ("votacao_candidato_munzona", "detalhe_votacao_munzona", "detalhe_votacao_secao"):
        expected = f"{kind}_{year}.zip"
        urls = {resource["url"] for resource in catalog["result"]["resources"]
                if resource.get("url", "").endswith("/" + expected)}
        if len(urls) != 1:
            raise ValueError(f"Fonte não identificada unicamente: {expected}")
        url = urls.pop()
        path = download(url, folder / expected)
        sources[kind] = {"url": url, "path": str(path), "csvs": inspect_zip(path, rows=1)}
    report = {"ano": year, "catalogo_url": catalog_url, "fontes": sources}
    write_json(folder / "manifesto.json", report)
    return report


def official_totals(year: int, root: Path = ROOT) -> dict[str, Any]:
    """Soma apenas o arquivo federal BR, evitando duplicação com BRASIL e UFs."""
    manifest = fetch_official(year, root)
    result: dict[str, Any] = {"ano": year, "fontes": manifest["fontes"], "candidatos": {}}
    with tempfile.TemporaryDirectory(prefix="apuracao-oficial-") as temporary, duckdb.connect() as connection:
        connection.execute("INSTALL encodings")
        connection.execute("LOAD encodings")
        connection.execute("SET memory_limit='1GB'")
        for kind, source in manifest["fontes"].items():
            with zipfile.ZipFile(source["path"]) as archive:
                members = [name for name in archive.namelist() if name.endswith(f"_{year}_BR.csv")]
                if len(members) != 1:
                    raise ValueError(f"Arquivo federal BR não identificado: {kind}")
                path = Path(temporary) / "oficial.csv"
                with archive.open(members[0]) as zipped, path.open("wb") as output:
                    shutil.copyfileobj(zipped, output, length=1024*1024)
            connection.execute("""CREATE OR REPLACE TEMP TABLE federal AS
                SELECT * FROM read_csv(?, delim=';', encoding='latin-1', all_varchar=true)
                WHERE CD_CARGO='1' AND NR_TURNO='2' AND SG_UE='BR'
            """, [str(path)])
            if kind == "votacao_candidato_munzona":
                result["candidatos"] = {str(number): int(total) for number,total in connection.execute("""
                    SELECT NR_CANDIDATO,sum(CAST(QT_VOTOS_NOMINAIS_VALIDOS AS BIGINT))
                    FROM federal GROUP BY NR_CANDIDATO
                """).fetchall()}
            elif kind == "detalhe_votacao_munzona":
                columns = {
                    "aptos":"QT_APTOS", "comparecimento":"QT_COMPARECIMENTO",
                    "votos_validos":"QT_TOTAL_VOTOS_VALIDOS", "brancos":"QT_VOTOS_BRANCOS",
                    "nulos":"QT_TOTAL_VOTOS_NULOS", "aptos_nao_instaladas":"QT_ELEITORES_SECOES_NAO_INSTALADAS",
                    "secoes_principais":"QT_SECOES_PRINCIPAIS", "secoes_agregadas":"QT_SECOES_AGREGADAS",
                    "secoes_nao_instaladas":"QT_SECOES_NAO_INSTALADAS",
                }
                values = connection.execute("SELECT " + ",".join(f"sum(CAST({column} AS BIGINT))" for column in columns.values()) + " FROM federal").fetchone()
                result["totais"] = dict(zip(columns, map(int,values)))
            else:
                connection.execute("""CREATE OR REPLACE TEMP TABLE section_detail AS SELECT
                    SG_UF AS uf,lpad(CD_MUNICIPIO,5,'0') AS cod_municipio,NM_MUNICIPIO AS nome_municipio,
                    CAST(NR_ZONA AS INTEGER) AS zona,CAST(NR_SECAO AS INTEGER) AS secao,
                    CAST(QT_APTOS AS BIGINT) AS aptos,CAST(QT_COMPARECIMENTO AS BIGINT) AS comparecimento,
                    CAST(QT_VOTOS_NOMINAIS AS BIGINT) AS votos_nominais,
                    CAST(QT_VOTOS_BRANCOS AS BIGINT) AS brancos,CAST(QT_VOTOS_NULOS AS BIGINT) AS nulos,
                    DT_RECEBIMENTO_BU_HOR_TSE AS recebido_hor_tse,
                    try_strptime(DT_RECEBIMENTO_BU_HOR_TSE,['%d/%m/%Y %H:%M:%S','%Y-%m-%d %H:%M:%S']) AS recebido_hor_tse_timestamp,
                    ST_SECAO_INSTALADA, ST_SECAO_ANULADA, DS_ORIGEM_VOTO
                    FROM federal
                """)
                target = root / "data" / "interim" / f"detalhe_oficial_{year}.parquet"
                target.parent.mkdir(parents=True,exist_ok=True)
                connection.execute("COPY section_detail TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",[str(target)])
    write_json(root / "data" / "raw" / "oficial" / str(year) / "totais.json",result)
    return result


if __name__ == "__main__":
    for year in (2018,2022,2026):
        result = official_totals(year)
        print(year,result["candidatos"],result["totais"],flush=True)
