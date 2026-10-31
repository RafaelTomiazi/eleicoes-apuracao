"""Ingestão dos boletins presidenciais em uma linha por seção."""

from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import duckdb

from apuracao.config import CANDIDATES
from apuracao.download import ROOT, ensure_directories, read_json, write_json


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


def aggregate_csv(connection: duckdb.DuckDBPyConnection, source: Path, year: int) -> None:
    """Agrega um CSV sem multiplicar os atributos repetidos da seção."""
    connection.execute("CREATE OR REPLACE TEMP TABLE bu AS SELECT * FROM read_csv(?, delim=';', encoding='latin-1', all_varchar=true)", [str(source)])
    columns = {column[0] for column in connection.execute("DESCRIBE bu").fetchall()}
    uf = '"SG_ UF"' if year == 2018 else '"SG_UF"'
    aggregated = '"DS_SECOES_AGREGADAS"' if year == 2026 else '"DS_AGREGADAS"'
    flashcard = '"CD_FLASCARD_URNA_EFETIVADA"' if year == 2018 else '"CD_FLASHCARD_URNA_EFETIVADA"'
    received = '"DT_BU_RECEBIDO"' if "DT_BU_RECEBIDO" in columns else "NULL::VARCHAR"
    emission = '"DT_EMISSAO_BU"' if "DT_EMISSAO_BU" in columns else "NULL::VARCHAR"
    pattern = "%Y-%m-%d %H:%M:%S" if year == 2026 else "%d/%m/%Y %H:%M:%S"
    a, b = CANDIDATES[year]["A"], CANDIDATES[year]["B"]
    connection.execute(f"""
        CREATE OR REPLACE TEMP TABLE normalized AS
        SELECT trim({uf}) AS uf, lpad(trim(CD_MUNICIPIO), 5, '0') AS cod_municipio,
               NM_MUNICIPIO AS nome_municipio, CAST(NR_ZONA AS INTEGER) AS zona,
               CAST(NR_SECAO AS INTEGER) AS secao,
               CASE WHEN NR_LOCAL_VOTACAO IN ('#NULO#','#NULO','#NE','-1','-3','') THEN NULL
                    ELSE CAST(NR_LOCAL_VOTACAO AS INTEGER) END AS local_votacao,
               CAST(QT_APTOS AS BIGINT) AS aptos,
               CAST(QT_COMPARECIMENTO AS BIGINT) AS comparecimento,
               CAST(QT_ABSTENCOES AS BIGINT) AS abstencoes,
               CAST(NR_VOTAVEL AS INTEGER) AS numero,
               lower(trim(DS_TIPO_VOTAVEL)) AS tipo, CAST(QT_VOTOS AS BIGINT) AS votos,
               {received} AS recebido_texto,
               try_strptime({received}, '{pattern}') AS recebido_em_registrado,
               try_strptime({emission}, '{pattern}') AS emitido_em_registrado,
               try_strptime(DT_ENCERRAMENTO, '{pattern}') AS encerramento_registrado,
               CASE WHEN {aggregated} IN ('#NULO#', '#NE', '-1', '-3', '') THEN NULL
                    ELSE {aggregated} END AS secoes_agregadas,
               {flashcard} AS cd_flashcard_urna_efetivada
        FROM bu WHERE trim(CD_CARGO_PERGUNTA)='1' AND lower(trim(DS_CARGO_PERGUNTA))='presidente'
                    AND trim(NR_TURNO)='2' AND CAST(ANO_ELEICAO AS INTEGER)={year}
    """)
    invalid = connection.execute(f"""
        SELECT count(*) FROM normalized WHERE votos IS NULL OR aptos IS NULL OR comparecimento IS NULL
          OR abstencoes IS NULL OR numero IS NULL OR uf IS NULL OR cod_municipio IS NULL
          OR zona IS NULL OR secao IS NULL OR tipo IS NULL
          OR votos < 0 OR aptos < 0 OR comparecimento < 0 OR abstencoes < 0
          OR comparecimento > aptos OR tipo NOT IN ('nominal','branco','nulo')
          OR (tipo='nominal' AND numero NOT IN ({a},{b}))
    """).fetchone()[0]
    if invalid:
        raise ValueError(f"{year}: {invalid} linhas com atributos ou votáveis inesperados")
    conflicts = connection.execute("""
        SELECT count(*) FROM (
          SELECT uf,cod_municipio,zona,secao FROM normalized GROUP BY ALL
          HAVING count(DISTINCT aptos)>1 OR count(DISTINCT comparecimento)>1
             OR count(DISTINCT abstencoes)>1 OR count(DISTINCT recebido_texto)>1
             OR count(DISTINCT secoes_agregadas)>1
             OR count(DISTINCT coalesce(local_votacao,-1))>1
        )
    """).fetchone()[0]
    if conflicts:
        raise ValueError(f"{year}: {conflicts} seções com atributos repetidos divergentes")
    connection.execute(f"""
        CREATE OR REPLACE TEMP TABLE batch AS
        SELECT uf,cod_municipio, max(nome_municipio) AS nome_municipio,zona,secao,
          max(local_votacao) AS local_votacao,
          max(aptos) AS aptos,max(comparecimento) AS comparecimento,max(abstencoes) AS abstencoes,
          coalesce(sum(votos) FILTER (WHERE tipo='nominal' AND numero={a}),0)::BIGINT AS votos_A,
          coalesce(sum(votos) FILTER (WHERE tipo='nominal' AND numero={b}),0)::BIGINT AS votos_B,
          coalesce(sum(votos) FILTER (WHERE tipo='nominal'),0)::BIGINT AS votos_validos,
          coalesce(sum(votos) FILTER (WHERE tipo='branco'),0)::BIGINT AS brancos,
          coalesce(sum(votos) FILTER (WHERE tipo='nulo'),0)::BIGINT AS nulos,
          max(recebido_texto) AS recebido_texto,
          max(recebido_em_registrado) AS recebido_em_registrado,
          max(emitido_em_registrado) AS emitido_em_registrado,
          max(encerramento_registrado) AS encerramento_registrado,
          max(secoes_agregadas) AS secoes_agregadas,
          max(cd_flashcard_urna_efetivada) AS cd_flashcard_urna_efetivada,
          uf='ZZ' AS exterior
        FROM normalized GROUP BY uf,cod_municipio,zona,secao
    """)
    connection.execute("CREATE TABLE IF NOT EXISTS sections AS SELECT * FROM batch WHERE false")
    connection.execute("INSERT INTO sections SELECT * FROM batch")


def ingest_year(year: int, root: Path = ROOT) -> dict[str, Any]:
    """Produz o Parquet e os diagnósticos sem perder os horários originais."""
    ensure_directories(root)
    folder = root / "data" / "raw" / "tse" / str(year)
    manifest = read_json(folder / "manifesto.json")
    with tempfile.TemporaryDirectory(prefix="apuracao-") as temporary, duckdb.connect() as connection:
        connection.execute("SET memory_limit='1GB'")
        connection.execute("INSTALL encodings")
        connection.execute("LOAD encodings")
        source = Path(temporary) / "bu.csv"
        for resource in manifest["recursos"]:
            with zipfile.ZipFile(folder / resource["arquivo_local"]) as archive:
                for csv_file in resource["csvs"]:
                    with archive.open(csv_file["arquivo"]) as zipped, source.open("wb") as output:
                        shutil.copyfileobj(zipped, output, length=1024 * 1024)
                    aggregate_csv(connection, source, year)
            print(f"{year}: {resource['uf']} agregado", flush=True)
        duplicates = connection.execute("""
          SELECT count(*) FROM (SELECT uf,cod_municipio,zona,secao FROM sections GROUP BY ALL HAVING count(*)>1)
        """).fetchone()[0]
        if duplicates:
            raise ValueError(f"Chave de seção duplicada: {duplicates}")
        balance = connection.execute("""
          SELECT count(*) FROM sections WHERE votos_A+votos_B<>votos_validos
            OR votos_validos+brancos+nulos<>comparecimento OR comparecimento+abstencoes<>aptos
        """).fetchone()[0]
        if balance:
            raise ValueError(f"Seções com balanço inconsistente de votos/eleitores: {balance}")
        totals = connection.execute("""
          SELECT count(*) AS secoes,sum(aptos) AS aptos,sum(comparecimento) AS comparecimento,
            sum(votos_A) AS votos_A,sum(votos_B) AS votos_B,sum(votos_validos) AS votos_validos,
            sum(brancos) AS brancos,sum(nulos) AS nulos,count(*) FILTER(WHERE exterior) AS secoes_exterior,
            count(*) FILTER(WHERE secoes_agregadas IS NOT NULL) AS urnas_com_agregadas,
            count(*) FILTER(WHERE recebido_em_registrado IS NULL) AS horarios_nulos,
            count(*) FILTER(WHERE recebido_texto IN ('#NULO#','#NE','-1','-3','')) AS sentinelas,
            count(*) FILTER(WHERE recebido_texto IS NOT NULL AND recebido_em_registrado IS NULL
                             AND recebido_texto NOT IN ('#NULO#','#NE','-1','-3','')) AS horarios_invalidos
          FROM sections
        """)
        totals = dict(zip((column[0] for column in totals.description), totals.fetchone()))
        by_uf = connection.execute("""
          SELECT uf,count(*) AS secoes,min(recebido_em_registrado) AS primeiro_recebido,
            min(encerramento_registrado) AS primeiro_encerramento,
            count(*) FILTER(WHERE recebido_em_registrado<encerramento_registrado) AS recebido_antes_encerramento
          FROM sections GROUP BY uf ORDER BY uf
        """).fetchall()
        ties = connection.execute("""
          SELECT count(*) AS instantes_empatados,coalesce(sum(n),0)::BIGINT AS secoes_em_empates,
            coalesce(max(n),0)::BIGINT AS maior_empate FROM (
              SELECT recebido_em_registrado,count(*) AS n FROM sections
              WHERE recebido_em_registrado IS NOT NULL GROUP BY 1 HAVING count(*)>1)
        """).fetchone()
        a,b = CANDIDATES[year]["A"],CANDIDATES[year]["B"]
        target = root / "data" / "interim" / f"secoes_{year}.parquet"
        partial = target.with_suffix(".parquet.part")
        connection.execute(f"""
          COPY (SELECT *, recebido_em_registrado AS recebido_em,
            map([{a},{b}], [votos_A,votos_B]) AS votos_por_numero,
            votos_A AS votos_{a}, votos_B AS votos_{b}
            FROM sections ORDER BY uf,cod_municipio,zona,secao)
          TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
        """, [str(partial)])
        partial.replace(target)
    report = {"ano":year,"totais":{key:int(value) for key,value in totals.items()},
              "empates":dict(zip(("instantes_empatados","secoes_em_empates","maior_empate"),ties)),
              "por_uf":[dict(zip(("uf","secoes","primeiro_recebido","primeiro_encerramento",
                                  "recebido_antes_encerramento"),
                                 [str(value) if hasattr(value,"isoformat") else value for value in row])) for row in by_uf],
              "fase":"agregação BU; atribuição de fuso registrada em validacao_{ano}.json"}
    write_json(root / "data" / "interim" / f"diagnostico_{year}.json", report)
    print(f"{year}: {totals['secoes']} BUs, balanços de votos e eleitores conferidos", flush=True)
    return report


def main() -> None:
    """Executa a ingestão ou lista os candidatos dos BUs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listar-candidatos", action="store_true")
    parser.add_argument("--ano", type=int, choices=(2018, 2022, 2026), nargs="+", default=[2018, 2022, 2026])
    args = parser.parse_args()
    for year in args.ano:
        if args.listar_candidatos:
            for number, name, party in presidential_candidates(year):
                print(f"CANDIDATO | {year} | {number} | {name} | {party}", flush=True)
        else:
            ingest_year(year)
            from apuracao.validation import document_validation, finalize_year

            finalize_year(year)
            document_validation()


if __name__ == "__main__":
    main()
