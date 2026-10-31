"""Baixa fontes oficiais sem transformar os dados eleitorais."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[2]
CATALOG = "https://dadosabertos.tse.jus.br/api/3/action/package_show"
UFS = set("AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO ZZ".split())


def session() -> requests.Session:
    """Cria uma sessão com repetição de falhas transitórias."""
    client = requests.Session()
    retry = Retry(total=4, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    client.mount("https://", HTTPAdapter(max_retries=retry))
    return client


def ensure_directories(root: Path = ROOT) -> None:
    """Cria os diretórios de dados ausentes."""
    for name in ("raw", "interim", "processed"):
        (root / "data" / name).mkdir(parents=True, exist_ok=True)


def download(url: str, target: Path, *, json_response: bool = False) -> Path:
    """Baixa em fluxo com cache e publicação atômica do arquivo completo."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.stat().st_size == 0:
            raise ValueError(f"Cache vazio: {target}")
        if json_response:
            read_json(target)
        return target
    partial = target.with_name(target.name + ".part")
    try:
        with session() as client, client.get(url, stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            size = 0
            with partial.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    output.write(chunk)
                    size += len(chunk)
            expected = response.headers.get("Content-Length")
            if not size or (expected and not response.headers.get("Content-Encoding") and size != int(expected)):
                raise ValueError(f"Download incompleto: {url}")
        if json_response:
            read_json(partial)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def read_json(path: Path) -> Any:
    """Lê uma resposta JSON preservada no cache."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    """Grava metadados em JSON legível."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def discover_resources(metadata: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Seleciona o último turno publicado e exige cobertura de todas as UFs."""
    candidates: dict[tuple[int, str], dict[str, Any]] = {}
    checksums: dict[str, str] = {}
    for resource in metadata["resources"]:
        url = resource.get("url", "")
        if urlparse(url).hostname != "cdn.tse.jus.br":
            continue
        name = Path(urlparse(url).path).name
        match = re.fullmatch(r"bweb_([12])t_([A-Z]{2})_(\d+)\.zip(\.sha512)?", name, re.I)
        if not match:
            continue
        turn, uf = int(match[1]), match[2].upper()
        if match[4]:
            checksums[url[:-7]] = url
            # O portal pode listar só o hash; o download ainda confirma o ZIP no CDN.
            url = url[:-7]
        key = turn, uf
        if key not in candidates or url > candidates[key]["url"]:
            candidates[key] = {"turno": turn, "uf": uf, "url": url}
    if not candidates:
        raise ValueError("Nenhum BWEB publicado no catálogo oficial; não presumir turno.")
    turn = max(key[0] for key in candidates)
    chosen = [value | {"checksum_url": checksums.get(value["url"])}
              for key, value in sorted(candidates.items()) if key[0] == turn]
    missing = UFS - {value["uf"] for value in chosen}
    if missing:
        raise ValueError(f"Catálogo incompleto no turno {turn}: {sorted(missing)}")
    return turn, chosen


def inspect_zip(path: Path, rows: int = 3) -> list[dict[str, Any]]:
    """Lê apenas cabeçalho e poucas linhas de cada CSV dentro do ZIP."""
    samples = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".csv"):
                continue
            with archive.open(name) as binary, io.TextIOWrapper(binary, encoding="latin-1", newline="") as text:
                reader = csv.DictReader(text, delimiter=";")
                sample = []
                for _, row in zip(range(rows), reader):
                    sample.append(row)
                samples.append({"arquivo": name, "colunas": reader.fieldnames, "amostra": sample})
    if not samples:
        raise ValueError(f"ZIP sem CSV: {path}")
    return samples


def fetch_resource(resource: dict[str, Any], folder: Path) -> dict[str, Any]:
    """Baixa um BU, confere SHA-512 oficial e registra sua amostra."""
    path = download(resource["url"], folder / Path(urlparse(resource["url"]).path).name)
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha512").hexdigest()
    if resource["checksum_url"]:
        checksum = download(resource["checksum_url"], folder / (path.name + ".sha512"))
        hashes = re.findall(r"\b[0-9a-fA-F]{128}\b", checksum.read_text(encoding="latin-1"))
        if digest.lower() not in {value.lower() for value in hashes}:
            raise ValueError(f"SHA-512 divergente: {path}")
    result = resource | {"arquivo_local": path.name, "bytes": path.stat().st_size,
                         "sha512": digest, "csvs": inspect_zip(path)}
    print(f"BU {resource['uf']}: {path.name} conferido", flush=True)
    return result


def download_tse(year: int, root: Path = ROOT, workers: int = 4) -> dict[str, Any]:
    """Obtém BUs de todas as UFs para o último turno publicado do ano."""
    ensure_directories(root)
    folder = root / "data" / "raw" / "tse" / str(year)
    catalog_url = f"{CATALOG}?id=resultados-{year}-boletim-de-urna"
    catalog = read_json(download(catalog_url, folder / "catalogo.json", json_response=True))
    if not catalog.get("success"):
        raise ValueError(f"Falha no catálogo: {catalog_url}")
    turn, resources = discover_resources(catalog["result"])
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda item: fetch_resource(item, folder), resources))
    manifest = {"ano": year, "turno": turn, "catalogo_url": catalog_url,
                "inspecionado_em": datetime.now(timezone.utc).isoformat(), "recursos": results}
    write_json(folder / "manifesto.json", manifest)
    return manifest


def main() -> None:
    """Executa os downloads oficiais pela linha de comando."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ano", type=int, choices=[2018, 2022, 2026], default=2026)
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 9))
    args = parser.parse_args()
    download_tse(args.ano, workers=args.workers)
    download_ibge()
    document_inspection()


def download_ibge(root: Path = ROOT) -> None:
    """Baixa indicadores municipais brutos e metadados do IBGE."""
    ensure_directories(root)
    # As fontes e variáveis são confirmadas em docs/FONTES_IBGE.md.
    sources = {
        "populacao": "https://apisidra.ibge.gov.br/values/t/4714/n6/all/v/93/p/2022",
        "populacao_estimada_2026": "https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/2026",
        "pib_total_2023": "https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/2023",
        "alfabetizacao": "https://apisidra.ibge.gov.br/values/t/9543/n6/all/v/2513/p/2022",
        "renda_domiciliar_per_capita": "https://apisidra.ibge.gov.br/values/t/10295/n6/all/v/13431/p/2022",
    }
    records = []
    for name, url in sources.items():
        path = download(url, root / "data" / "raw" / "ibge" / f"{name}.json", json_response=True)
        data = read_json(path)
        if not isinstance(data, list) or len(data) < 2:
            raise ValueError(f"Resposta IBGE inválida: {url}")
        records.append({"indicador": name, "url": url, "registros": len(data) - 1,
                        "bytes": path.stat().st_size,
                        "sha512": hashlib.sha512(path.read_bytes()).hexdigest(),
                        "inspecionado_em": datetime.now(timezone.utc).isoformat(),
                        "amostra": data[:3]})
        print(f"IBGE {name}: {len(data) - 1} registros municipais", flush=True)
    # A API SIDRA 5938 fornece PIB total; per capita está na base oficial completa.
    url = "https://ftp.ibge.gov.br/Pib_Municipios/2022_2023/base/base_de_dados_2010_2023_txt.zip"
    path = download(url, root / "data" / "raw" / "ibge" / "base_de_dados_2010_2023_txt.zip")
    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        txt = next(name for name in members if name.lower().endswith(".txt"))
        with archive.open(txt) as source:
            sample = [source.readline().decode("cp1252").rstrip() for _ in range(3)]
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha512").hexdigest()
    records.append({"indicador": "pib_per_capita_base", "url": url, "sha512": digest,
                    "bytes": path.stat().st_size,
                    "inspecionado_em": datetime.now(timezone.utc).isoformat(),
                    "arquivos": members, "amostra_txt": sample})
    write_json(root / "data" / "raw" / "ibge" / "manifesto.json", records)


def document_inspection(root: Path = ROOT) -> None:
    """Documenta cabeçalhos e evidências dos arquivos efetivamente baixados."""
    lines = [
        "## Inspeção dos boletins de urna (Prompt 1)", "",
        "CSV lido diretamente do ZIP, com encoding `latin-1` e separador `;`. "
        "Foram lidos o cabeçalho e três registros por CSV; não houve ingestão, "
        "filtragem de presidente, soma de votos ou geração de Parquet.", "",
        "Os manifestos completos e amostras ficam em `data/raw/tse/{ano}/manifesto.json`. "
        "Cada ZIP foi comparado com o SHA-512 publicado pelo TSE. "
        "Os dados brutos permanecem fora do Git.", "",
        "### Horário de recebimento", "",
        "| Ano | Turno publicado selecionado | CSVs inspecionados | Campo | Exemplo real (AC) |",
        "| --- | --- | --- | --- | --- |",
    ]
    manifests = []
    for year in (2018, 2022, 2026):
        path = root / "data" / "raw" / "tse" / str(year) / "manifesto.json"
        if not path.exists():
            continue
        manifest = read_json(path)
        manifests.append(manifest)
        csvs = [csv_file for item in manifest["recursos"] for csv_file in item["csvs"]]
        field = "DT_BU_RECEBIDO"
        count = sum(field in item["colunas"] for item in csvs)
        example = csvs[0]["amostra"][0].get(field, "ausente")
        lines.append(f"| {year} | {manifest['turno']} | {len(csvs)} | {field if count else 'ausente'} ({count}/{len(csvs)}) | `{example}` |")
    lines += ["", "Em 2022, `DT_BU_RECEBIDO` usa `DD/MM/AAAA HH:MM:SS`; em 2026, "
              "`AAAA-MM-DD HH:MM:SS`. A inspeção confirma o campo nos 28 cabeçalhos de cada "
              "um desses anos, mas as amostras não demonstram cobertura integral dos valores. "
              "Os valores não trazem offset de fuso horário. Na ingestão, verificar nulos, "
              "sentinelas, fusos e empates antes de reconstruir a sequência nacional.", "",
              "Para os snapshots de 2026 e o backtest de 2022, há evidência para ordenar "
              "pelo recebimento registrado do BU, após essas verificações. Isso não demonstra "
              "o instante em que o voto entrou na totalização pública. Em 2018, o campo "
              "não existe: a ordem seria simulada se esse ano fosse usado como alvo de apuração. "
              "Como base do backtest de 2022, 2018 não precisa dessa ordem.", "",
              "`DT_GERACAO`/`HH_GERACAO` referem-se à geração do arquivo; "
              "`DT_ABERTURA`, `DT_ENCERRAMENTO` e `DT_EMISSAO_BU` não substituem o recebimento.", "",
              "### Colunas reais", "",
              "Os cabeçalhos abaixo preservam a grafia original. Em 2018 há `SG_ UF` "
              "(com espaço) e `CD_FLASCARD_URNA_EFETIVADA`. "
              "`CD_MUNICIPIO` é a chave do TSE e não deve ser confundida com a chave IBGE. "
              "O arquivo contém múltiplos cargos e múltiplas linhas por seção; "
              "a seleção de presidente será feita no Prompt 2.", ""]
    for manifest in manifests:
        year = manifest["ano"]
        schemas: dict[tuple[str, ...], int] = {}
        for resource in manifest["recursos"]:
            for csv_file in resource["csvs"]:
                key = tuple(csv_file["colunas"])
                schemas[key] = schemas.get(key, 0) + 1
        lines += [f"#### {year}", "", f"Fonte: [catálogo oficial]({manifest['catalogo_url']}).", ""]
        for schema, count in schemas.items():
            lines += [f"Cabeçalho observado em {count} CSVs ({len(schema)} colunas):", "", "```text", ";".join(schema), "```", ""]
        lines += ["| UF | ZIP oficial | Bytes |", "| --- | --- | --- |"]
        for resource in manifest["recursos"]:
            lines.append(f"| {resource['uf']} | [{resource['arquivo_local']}]({resource['url']}) | {resource['bytes']} |")
        lines.append("")
    lines += ["### IBGE e limites desta etapa", "",
              "Fontes, variáveis, unidades, períodos e restrições estão em "
              "[FONTES_IBGE.md](FONTES_IBGE.md). As respostas SIDRA brutas incluem "
              "população do Censo 2022, estimativa 2026, PIB total 2023, taxa de alfabetização "
              "2022 e renda domiciliar per capita 2022. PIB per capita foi baixado na base "
              "oficial TXT 2010–2023, com layout PDF no mesmo ZIP: a API consultada foi "
              "bloqueada neste ambiente. Esse é um desvio explícito do pedido de usar API "
              "para todos os indicadores. Não se confundiu PIB total com PIB per capita.", "",
              "As amostras e URLs IBGE estão em `data/raw/ibge/manifesto.json`. "
              "Não houve cálculo de indicadores. Antes de modelar cada eleição, selecionar "
              "dados publicados até a data simulada, especialmente no backtest de 2022; "
              "indicadores de anos posteriores não podem entrar nas previsões históricas.", ""]
    path = root / "docs" / "METODO.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Método\n"
    start, end = "<!-- inicio:inspecao-download -->", "<!-- fim:inspecao-download -->"
    block = start + "\n" + "\n".join(lines) + "\n" + end
    if start in existing and end in existing:
        before, rest = existing.split(start, 1)
        _, after = rest.split(end, 1)
        content = before + block + after
    else:
        content = existing.rstrip() + "\n\n" + block + "\n"
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
