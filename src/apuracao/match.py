"""Pareamento histórico em cascata, usando somente chaves e votos do TSE."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import duckdb

from apuracao.download import ROOT, ensure_directories, read_json, write_json

BASE_YEARS = {2022: 2018, 2026: 2022}
LEVELS = ("secao", "local", "zona", "municipio", "uf")
MIN_LOCAL_COVERAGE = 0.90


def build_cascade(connection: duckdb.DuckDBPyConnection) -> None:
    """Pareia as tabelas alvo e base sem usar votos do ano alvo nas proporções."""
    for table in ("alvo", "base"):
        connection.execute(f"CREATE OR REPLACE TEMP TABLE {table}_bu AS SELECT * FROM {table} WHERE tem_bu")
        duplicates = connection.execute(f"""
            SELECT count(*) FROM (SELECT uf,cod_municipio,zona,secao FROM {table}_bu
            GROUP BY ALL HAVING count(*)>1)
        """).fetchone()[0]
        if duplicates:
            raise ValueError(f"Chaves duplicadas no {table}: {duplicates}")
    keys = {
        "secao": ["uf", "cod_municipio", "zona", "secao"],
        "local": ["uf", "cod_municipio", "zona", "local_votacao"],
        "zona": ["uf", "cod_municipio", "zona"],
        "municipio": ["uf", "cod_municipio"],
        "uf": ["uf"],
    }
    for level, columns in keys.items():
        grouping = ",".join(columns)
        # As taxas são razões dos totais, e não médias simples de percentuais.
        connection.execute(f"""
            CREATE OR REPLACE TEMP TABLE historico_{level} AS SELECT {grouping},
                sum(votos_A)::DOUBLE / nullif(sum(votos_A+votos_B),0) AS pct_A_base,
                sum(comparecimento)::DOUBLE / nullif(sum(aptos),0) AS comparec_base,
                sum(comparecimento-votos_A-votos_B)::DOUBLE / nullif(sum(comparecimento),0) AS bn_base,
                count(*) AS secoes_base_no_grupo,
                sum(votos_A+votos_B)::BIGINT AS votos_validos_base_no_grupo,
                sum(aptos)::BIGINT AS aptos_base_no_grupo
            FROM base_bu GROUP BY {grouping}
            HAVING sum(votos_A+votos_B)>0 AND sum(aptos)>0
        """)
    joins = []
    for index, (level, columns) in enumerate(keys.items()):
        condition = " AND ".join(f"t.{column}=h{index}.{column}" for column in columns)
        joins.append(f"LEFT JOIN historico_{level} h{index} ON {condition}")
    choice = "CASE " + " ".join(f"WHEN h{i}.pct_A_base IS NOT NULL THEN '{level}'" for i,level in enumerate(LEVELS)) + " END"
    values = ",".join(
        f"coalesce({','.join(f'h{i}.{column}' for i in range(len(LEVELS)))}) AS {column}"
        for column in ("pct_A_base","comparec_base","bn_base","secoes_base_no_grupo","votos_validos_base_no_grupo","aptos_base_no_grupo")
    )
    connection.execute(f"""
        CREATE OR REPLACE TEMP TABLE pareado AS
        SELECT t.*, {choice} AS nivel_pareamento,
            h0.pct_A_base IS NOT NULL AS pareada, {values}
        FROM alvo_bu t {' '.join(joins)}
    """)
    invalid = connection.execute("""
        SELECT count(*) FROM pareado WHERE nivel_pareamento IS NULL
          OR pct_A_base IS NULL OR pct_A_base NOT BETWEEN 0 AND 1
          OR comparec_base IS NULL OR comparec_base NOT BETWEEN 0 AND 1
          OR bn_base IS NULL OR bn_base NOT BETWEEN 0 AND 1
    """).fetchone()[0]
    if invalid:
        raise ValueError(f"{invalid} seções sem base válida até o nível UF")


def coverage_report(connection: duckdb.DuckDBPyConnection, year: int, base_year: int) -> dict[str, Any]:
    """Mede a cobertura pelos aptos e pelas seções com BU do ano alvo."""
    sections, eligible = connection.execute("SELECT count(*),sum(aptos) FROM pareado").fetchone()
    if not sections or not eligible:
        raise ValueError("Ano alvo sem seções com BU e aptos positivos")
    grouped = {level:(count,aptos) for level,count,aptos in connection.execute("""
        SELECT nivel_pareamento,count(*),sum(aptos) FROM pareado GROUP BY nivel_pareamento
    """).fetchall()}
    levels = []
    for level in LEVELS:
        count, aptos = grouped.get(level,(0,0))
        levels.append({"nivel":level,"secoes":count,"aptos":aptos,
                       "pct_secoes":100*count/sections,"pct_aptos":100*aptos/eligible})
    combined = sum(item["aptos"] for item in levels if item["nivel"] in ("secao","local"))/eligible
    return {"ano":year,"ano_base":base_year,"secoes_alvo":sections,"aptos_alvo":eligible,
            "niveis":levels,"cobertura_aptos_secao_local":combined,
            "meta_estrita":MIN_LOCAL_COVERAGE,"aprovado":combined>MIN_LOCAL_COVERAGE}


def require_coverage(report: dict[str, Any]) -> None:
    """Interrompe a publicação quando seção e local não cobrem mais de 90%."""
    if report["cobertura_aptos_secao_local"] <= MIN_LOCAL_COVERAGE:
        raise ValueError(f"{report['ano']}: seção+local cobre {100*report['cobertura_aptos_secao_local']:.4f}% dos aptos; meta >90%. Parar para revisão, sem alterar a meta.")


def match_year(year: int, root: Path = ROOT) -> dict[str, Any]:
    """Gera o pareamento validado e o relatório de cobertura do ano alvo."""
    base_year = BASE_YEARS[year]
    ensure_directories(root)
    with duckdb.connect() as connection:
        connection.execute("SET memory_limit='1GB'")
        for table, current_year in (("alvo",year),("base",base_year)):
            path = root / "data" / "interim" / f"secoes_{current_year}.parquet"
            connection.execute(f"CREATE TEMP TABLE {table} AS SELECT * FROM read_parquet(?)",[str(path)])
        build_cascade(connection)
        report = coverage_report(connection,year,base_year)
        print(f"\n{year} <- {base_year}: {report['secoes_alvo']} seções; {report['aptos_alvo']} aptos",flush=True)
        for level in report["niveis"]:
            print(f"{level['nivel']:10} {level['secoes']:8} seções ({level['pct_secoes']:7.3f}%) | {level['aptos']:12} aptos ({level['pct_aptos']:7.3f}%)",flush=True)
        print(f"Seção+local: {100*report['cobertura_aptos_secao_local']:.4f}% dos aptos",flush=True)
        write_json(root / "data" / "processed" / f"cobertura_{year}.json",report)
        document_matching(root)
        require_coverage(report)
        target = root / "data" / "processed" / f"pareado_{year}.parquet"
        partial = target.with_suffix(".parquet.part")
        connection.execute("COPY (SELECT *, ?::INTEGER AS ano_base FROM pareado ORDER BY uf,cod_municipio,zona,secao) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",[base_year,str(partial)])
        partial.replace(target)
    return report


def document_matching(root: Path = ROOT) -> None:
    """Registra a cobertura dos arquivos locais no método e em JSON versionado."""
    reports = []
    for year in BASE_YEARS:
        path = root / "data" / "processed" / f"cobertura_{year}.json"
        if path.exists():
            reports.append(read_json(path))
    write_json(root / "docs" / "COBERTURA_PAREAMENTO.json",reports)
    lines = ["## Cobertura do pareamento (Prompt 3)","",
             "Denominador: apenas seções com `tem_bu=True` e seus aptos no ano alvo. "
             "As proporções históricas usam apenas BUs do ano base.","",
             "| Alvo ← base | Nível | Seções | % seções | Aptos | % aptos |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for report in reports:
        for level in report["niveis"]:
            lines.append(f"| {report['ano']} ← {report['ano_base']} | {level['nivel']} | {level['secoes']} | {level['pct_secoes']:.4f} | {level['aptos']} | {level['pct_aptos']:.4f} |")
    for report in reports:
        lines += ["",f"Seção + local em {report['ano']}: **{100*report['cobertura_aptos_secao_local']:.4f}% dos aptos**; meta estrita >90%: {'aprovada' if report['aprovado'] else 'NÃO atingida; execução interrompida' }.",""]
    method = root / "docs" / "METODO.md"
    existing = method.read_text(encoding="utf-8") if method.exists() else "# Método\n"
    start,end = "<!-- inicio:cobertura-pareamento -->","<!-- fim:cobertura-pareamento -->"
    block = start + "\n" + "\n".join(lines) + "\n" + end
    if start in existing and end in existing:
        before,rest = existing.split(start,1)
        _,after = rest.split(end,1)
        content = before+block+after
    else:
        content = existing.rstrip()+"\n\n"+block+"\n"
    method.write_text(content,encoding="utf-8")


def main() -> None:
    """Executa os pareamentos 2022←2018 e 2026←2022."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ano",type=int,choices=tuple(BASE_YEARS),nargs="+",default=list(BASE_YEARS))
    args = parser.parse_args()
    for year in args.ano:
        match_year(year)


if __name__ == "__main__":
    main()
