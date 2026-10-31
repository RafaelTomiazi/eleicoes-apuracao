"""Inspeção inicial da ingestão, sem atribuição de candidatos aos lados A/B."""

from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path

import duckdb

from apuracao.download import ROOT, read_json


def presidential_candidates(year: int, root: Path = ROOT) -> list[tuple[str, str, str]]:
    """Lista candidatos nominais reais de todos os BUs presidenciais do ano."""
    folder = root / "data" / "raw" / "tse" / str(year)
    manifest = read_json(folder / "manifesto.json")
    candidates: set[tuple[str, str, str]] = set()
    with duckdb.connect() as connection, tempfile.TemporaryDirectory(prefix="apuracao-") as temporary:
        connection.execute("SET memory_limit='1GB'")
        connection.execute("INSTALL encodings")
        connection.execute("LOAD encodings")
        source = Path(temporary) / "bu.csv"
        for resource in manifest["recursos"]:
            with zipfile.ZipFile(folder / resource["arquivo_local"]) as archive:
                for csv_file in resource["csvs"]:
                    with archive.open(csv_file["arquivo"]) as zipped, source.open("wb") as output:
                        shutil.copyfileobj(zipped, output, length=1024 * 1024)
                    rows = connection.execute(
                        """
                        SELECT DISTINCT NR_VOTAVEL, NM_VOTAVEL, SG_PARTIDO
                        FROM read_csv(?, delim=';', encoding='latin-1', all_varchar=true)
                        WHERE trim(CD_CARGO_PERGUNTA) = '1'
                          AND lower(trim(DS_CARGO_PERGUNTA)) = 'presidente'
                          AND trim(NR_TURNO) = '2'
                          AND lower(trim(DS_TIPO_VOTAVEL)) = 'nominal'
                        """,
                        [str(source)],
                    ).fetchall()
                    candidates.update(rows)
            print(f"{year}: {resource['uf']} inspecionado", flush=True)
    if len(candidates) != 2:
        raise ValueError(f"Esperados dois candidatos, encontrados: {sorted(candidates)}")
    return sorted(candidates)


def main() -> None:
    """Lista os candidatos para confirmação humana do mapeamento A/B."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listar-candidatos", action="store_true", required=True)
    parser.add_argument("--ano", type=int, choices=(2018, 2022, 2026), nargs="+", default=[2018, 2022, 2026])
    args = parser.parse_args()
    for year in args.ano:
        for number, name, party in presidential_candidates(year):
            print(f"CANDIDATO | {year} | {number} | {name} | {party}", flush=True)
    print("Aguardando confirmação do mapeamento A/B; nenhuma atribuição foi criada.")


if __name__ == "__main__":
    main()
