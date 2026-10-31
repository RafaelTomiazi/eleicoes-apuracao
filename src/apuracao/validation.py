"""Conciliação de cobertura, horários e totais com fontes oficiais independentes."""

from pathlib import Path
from typing import Any

import duckdb

from apuracao.config import CANDIDATES, OFFICIAL_TOTALS, RECEIVED_TIMEZONE
from apuracao.download import ROOT, read_json, write_json
from apuracao.official import official_totals


def finalize_year(year: int, root: Path = ROOT) -> dict[str, Any]:
    """Concilia as seções sem BU e valida o resultado nacional antes de publicar."""
    official = official_totals(year, root)
    path = root / "data" / "interim" / f"secoes_{year}.parquet"
    detail = root / "data" / "interim" / f"detalhe_oficial_{year}.parquet"
    a,b = CANDIDATES[year]["A"],CANDIDATES[year]["B"]
    with duckdb.connect() as connection:
        connection.execute("SET TimeZone='America/Sao_Paulo'")
        connection.execute("CREATE TEMP TABLE bu AS SELECT * FROM read_parquet(?)",[str(path)])
        # A finalização pode ser repetida sobre um arquivo já conciliado.
        if "tem_bu" in {row[0] for row in connection.execute("DESCRIBE bu").fetchall()}:
            connection.execute("DELETE FROM bu WHERE NOT tem_bu")
        connection.execute("CREATE TEMP TABLE official_sections AS SELECT * FROM read_parquet(?)",[str(detail)])
        duplicates = connection.execute("SELECT count(*) FROM (SELECT uf,cod_municipio,zona,secao FROM official_sections GROUP BY ALL HAVING count(*)>1)").fetchone()[0]
        if duplicates:
            raise ValueError("Chave duplicada no detalhe oficial")
        extra = connection.execute("SELECT count(*) FROM bu ANTI JOIN official_sections USING(uf,cod_municipio,zona,secao)").fetchone()[0]
        if extra:
            raise ValueError(f"{extra} BUs sem correspondência na fonte independente")
        connection.execute("CREATE TEMP TABLE missing AS SELECT d.* FROM official_sections d ANTI JOIN bu b USING(uf,cod_municipio,zona,secao)")
        if connection.execute("SELECT count(*) FROM missing WHERE comparecimento<>0 OR votos_nominais<>0 OR brancos<>0 OR nulos<>0").fetchone()[0]:
            raise ValueError("Seções sem BU possuem votos; exige conciliação manual")
        gaps = connection.execute("SELECT count(*),coalesce(sum(aptos),0) FROM missing").fetchone()
        time_comparison = connection.execute("""
          SELECT count(*),count(*) FILTER(WHERE b.recebido_em_registrado=d.recebido_hor_tse_timestamp)
          FROM bu b JOIN official_sections d USING(uf,cod_municipio,zona,secao)
        """).fetchone()
        if year != 2018 and time_comparison[0] != time_comparison[1]:
            raise ValueError("Horários do BU divergem da Hora TSE; não atribuir fuso automaticamente")
        zone = RECEIVED_TIMEZONE[year]
        received = f"timezone('{zone}', b.recebido_em_registrado)" if zone else "NULL::TIMESTAMPTZ"
        connection.execute(f"""
          CREATE TEMP TABLE final AS SELECT
            d.uf,d.cod_municipio,d.nome_municipio,d.zona,d.secao,
            CASE WHEN b.uf IS NOT NULL THEN b.local_votacao ELSE d.local_votacao END AS local_votacao,d.aptos,
            coalesce(b.comparecimento,0)::BIGINT AS comparecimento,
            d.aptos-coalesce(b.comparecimento,0)::BIGINT AS abstencoes,
            coalesce(b.votos_A,0)::BIGINT AS votos_A,coalesce(b.votos_B,0)::BIGINT AS votos_B,
            coalesce(b.votos_validos,0)::BIGINT AS votos_validos,
            coalesce(b.brancos,0)::BIGINT AS brancos,coalesce(b.nulos,0)::BIGINT AS nulos,
            b.recebido_texto,b.recebido_em_registrado,{received} AS recebido_em,
            b.emitido_em_registrado,b.encerramento_registrado,b.secoes_agregadas,
            b.cd_flashcard_urna_efetivada,d.uf='ZZ' AS exterior,
            b.uf IS NOT NULL AS tem_bu,b.uf IS NOT NULL AS apta_simulacao,
            CASE WHEN b.uf IS NOT NULL THEN 'bweb' ELSE 'detalhe_oficial_sem_bu' END AS origem_registro,
            d.ST_SECAO_INSTALADA AS situacao_instalada_oficial,d.ST_SECAO_ANULADA AS situacao_anulada_oficial,
            d.recebido_hor_tse AS recebido_hor_tse_oficial,
            map([{a},{b}], [coalesce(b.votos_A,0)::BIGINT,coalesce(b.votos_B,0)::BIGINT]) AS votos_por_numero,
            coalesce(b.votos_A,0)::BIGINT AS votos_{a},coalesce(b.votos_B,0)::BIGINT AS votos_{b}
          FROM official_sections d LEFT JOIN bu b USING(uf,cod_municipio,zona,secao)
        """)
        # Não substituir silenciosamente o eleitorado do BU pelo detalhe oficial.
        differences = connection.execute("""
          SELECT count(*) FROM bu b JOIN official_sections d USING(uf,cod_municipio,zona,secao)
          WHERE b.aptos<>d.aptos OR b.comparecimento<>d.comparecimento
        """).fetchone()[0]
        if differences:
            raise ValueError(f"Atributos BU/oficial divergentes em {differences} seções")
        totals = connection.execute("""SELECT count(*) AS secoes,sum(aptos) AS aptos,sum(comparecimento) AS comparecimento,
            sum(votos_A) AS votos_A,sum(votos_B) AS votos_B,sum(votos_validos) AS votos_validos,
            sum(brancos) AS brancos,sum(nulos) AS nulos,count(*) FILTER(WHERE tem_bu) AS secoes_com_bu,
            count(*) FILTER(WHERE exterior) AS secoes_exterior FROM final""")
        observed = dict(zip((column[0] for column in totals.description),map(int,totals.fetchone())))
        expected = official["totais"] | {"votos_A":official["candidatos"][str(a)],"votos_B":official["candidatos"][str(b)]}
        for key in ("aptos","comparecimento","votos_A","votos_B","votos_validos","brancos","nulos"):
            if observed[key] != expected[key]:
                raise ValueError(f"{year}: {key}: BU/conciliado={observed[key]} oficial={expected[key]}")
        for key,value in OFFICIAL_TOTALS[year].items():
            if observed[key] != value:
                raise ValueError(f"Snapshot oficial alterado em {year}: {key}")
        uf_stats = connection.execute("""SELECT uf,count(*) AS secoes_com_bu,
            min(recebido_em_registrado) AS primeiro_recebido,
            min(encerramento_registrado) AS primeiro_encerramento,
            quantile_cont(date_diff('second',emitido_em_registrado,recebido_em_registrado),0.01) AS p01_seg_emissao_recebimento
            FROM final WHERE tem_bu GROUP BY uf ORDER BY uf""").fetchall()
        partial = path.with_suffix(".parquet.part")
        connection.execute("COPY (SELECT * FROM final ORDER BY uf,cod_municipio,zona,secao) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",[str(partial)])
        partial.replace(path)
        missing_rows = connection.execute("SELECT uf,cod_municipio,zona,secao,aptos,ST_SECAO_INSTALADA,ST_SECAO_ANULADA FROM missing ORDER BY ALL").fetchall()
    report = {"ano":year,"totais":observed,"totais_oficiais":expected,
              "secoes_sem_bu":gaps[0],"aptos_sem_bu":gaps[1],
              "horarios_comparados":time_comparison[0],"horarios_iguais_hora_tse":time_comparison[1],
              "fuso_recebido":zone,"fuso_status":"inferência documentada" if zone else "ausente no BU",
              "pct_A":100*observed["votos_A"]/observed["votos_validos"],
              "por_uf":[[str(value) if hasattr(value,"isoformat") else value for value in row] for row in uf_stats],
              "ausentes_no_bu":missing_rows,
              "fontes":{kind:{"url":source["url"],"csvs":[c["arquivo"] for c in source["csvs"] if c["arquivo"].endswith(f"_{year}_BR.csv")],
                              "colunas":next(c["colunas"] for c in source["csvs"] if c["arquivo"].endswith(f"_{year}_BR.csv"))}
                        for kind,source in official["fontes"].items()}}
    write_json(root / "data" / "interim" / f"validacao_{year}.json",report)
    print(f"{year}: {observed['secoes']} seções, {gaps[0]} sem BU; totais exatos",flush=True)
    return report


def document_validation(root: Path = ROOT) -> None:
    """Versiona evidências de cobertura, totais, campos reais e horários."""
    reports = []
    for year in (2018,2022,2026):
        report = root / "data" / "interim" / f"validacao_{year}.json"
        diagnostic = root / "data" / "interim" / f"diagnostico_{year}.json"
        if report.exists() and diagnostic.exists():
            raw_diagnostic = read_json(diagnostic)
            raw_diagnostic.pop("fuso",None)
            reports.append(read_json(report) | {"diagnostico_bu":raw_diagnostic})
    write_json(root / "docs" / "VALIDACAO_INGESTAO.json",reports)


if __name__ == "__main__":
    for year in (2018,2022,2026):
        finalize_year(year)
    document_validation()
