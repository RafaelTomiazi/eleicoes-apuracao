"""Verifica hierarquia, ponderação, agregações e cobertura real do pareamento."""

from collections.abc import Iterator

import duckdb
import pytest

from apuracao.download import ROOT
from apuracao.match import build_cascade, coverage_report, require_coverage


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    """Cria seções com taxas e tamanhos distintos para exercitar a cascata."""
    connection = duckdb.connect()
    connection.execute("""
        CREATE TABLE base AS SELECT * FROM (VALUES
          ('SP','00001',1,1,10,100,80,24,56,true,'100 / 101'),
          ('SP','00001',1,2,10,300,120,96,24,true,NULL),
          ('SP','00001',1,3,20,100,100,50,50,true,NULL),
          ('SP','00001',2,4,30,200,100,90,10,true,NULL),
          ('SP','00002',9,9,90,100,60,0,60,true,NULL),
          ('SP','00001',1,999,10,1000,0,0,0,false,NULL),
          ('ZZ','99999',1,1,1,10,5,5,0,true,NULL)
        ) t(uf,cod_municipio,zona,secao,local_votacao,aptos,comparecimento,votos_A,votos_B,tem_bu,secoes_agregadas)
    """)
    connection.execute("""
        CREATE TABLE alvo AS SELECT * FROM (VALUES
          ('SP','00001',1,1,999,100,99,99,0,true),
          ('SP','00001',1,100,10,100,99,99,0,true),
          ('SP','00001',1,101,999,100,99,99,0,true),
          ('SP','00001',8,102,999,100,99,99,0,true),
          ('SP','00003',8,103,999,100,99,99,0,true),
          ('ZZ','99998',1,2,1,100,99,99,0,true),
          ('SP','00001',1,999,10,5000,0,0,0,false)
        ) t(uf,cod_municipio,zona,secao,local_votacao,aptos,comparecimento,votos_A,votos_B,tem_bu)
    """)
    try:
        yield connection
    finally:
        connection.close()


def test_cascade_weights_and_aggregated_members(connection: duckdb.DuckDBPyConnection) -> None:
    """Usa principais uma vez e aplica taxas ponderadas no nível mais próximo."""
    build_cascade(connection)
    result = {section:(level,pct,turnout) for section,level,pct,turnout in connection.execute(
        "SELECT secao,nivel_pareamento,pct_A_base,comparec_base FROM pareado").fetchall()}
    expected = {1:("secao",0.3,0.8),100:("local",0.6,0.5),101:("zona",170/300,300/500),
                102:("municipio",260/400,400/700),103:("uf",260/460,460/800),2:("uf",1.0,0.5)}
    assert result.keys() == expected.keys()
    for section,(level,pct,turnout) in expected.items():
        assert result[section][0] == level
        assert result[section][1:] == pytest.approx((pct,turnout))
    assert connection.execute("SELECT count(*) FROM pareado WHERE NOT tem_bu").fetchone()[0] == 0
    report = coverage_report(connection,2022,2018)
    assert report["aptos_alvo"] == 600
    assert report["secoes_alvo"] == 6
    assert report["cobertura_aptos_secao_local"] == pytest.approx(1/3)


def test_target_votes_do_not_change_historical_features(connection: duckdb.DuckDBPyConnection) -> None:
    """Evita vazamento de votos do ano alvo para as taxas históricas."""
    build_cascade(connection)
    before = connection.execute("SELECT secao,pct_A_base,comparec_base FROM pareado ORDER BY secao").fetchall()
    connection.execute("UPDATE alvo SET votos_A=0,votos_B=10000,comparecimento=0")
    build_cascade(connection)
    assert connection.execute("SELECT secao,pct_A_base,comparec_base FROM pareado ORDER BY secao").fetchall() == before


def test_zero_valid_votes_fall_back_without_division_by_zero(connection: duckdb.DuckDBPyConnection) -> None:
    """Avança ao local quando a seção histórica não tem votos válidos."""
    connection.execute("UPDATE alvo SET local_votacao=10 WHERE uf='SP' AND secao=1")
    connection.execute("UPDATE base SET votos_A=0,votos_B=0 WHERE uf='SP' AND secao=1")
    build_cascade(connection)
    row = connection.execute("SELECT nivel_pareamento,pct_A_base,comparec_base FROM pareado WHERE uf='SP' AND secao=1").fetchone()
    assert row[0] == "local"
    assert row[1:] == pytest.approx((96/120,200/400))


def test_missing_uf_has_no_silent_national_fallback(connection: duckdb.DuckDBPyConnection) -> None:
    """Recusa alvo sem base na UF em vez de inventar uma média nacional."""
    connection.execute("UPDATE alvo SET uf='AC' WHERE secao=103")
    with pytest.raises(ValueError,match="sem base válida"):
        build_cascade(connection)


def test_duplicate_keys_cannot_multiply_matches(connection: duckdb.DuckDBPyConnection) -> None:
    """Recusa duplicação que inflaria a cobertura e o número de seções."""
    connection.execute("INSERT INTO base SELECT * FROM base WHERE uf='SP' AND secao=1")
    with pytest.raises(ValueError,match="Chaves duplicadas"):
        build_cascade(connection)


@pytest.mark.parametrize("coverage",[0.89,0.90])
def test_strict_coverage_gate_is_not_relaxed(coverage: float) -> None:
    """Exige mais de 90% dos aptos para publicar o pareamento."""
    with pytest.raises(ValueError,match="Parar para revisão"):
        require_coverage({"ano":2026,"cobertura_aptos_secao_local":coverage})


@pytest.mark.parametrize("year",[2022,2026])
def test_real_matching_coverage_and_target_population(year: int) -> None:
    """Confere a meta com os arquivos reais e a preservação da população alvo."""
    path = ROOT / "data" / "processed" / f"pareado_{year}.parquet"
    target = ROOT / "data" / "interim" / f"secoes_{year}.parquet"
    if not path.exists() or not target.exists():
        pytest.skip("Execute apuracao.ingest e apuracao.match para os dados reais")
    with duckdb.connect() as connection:
        connection.execute("CREATE TEMP TABLE pareado AS SELECT * FROM read_parquet(?)",[str(path)])
        report = coverage_report(connection,year,2018 if year==2022 else 2022)
        require_coverage(report)
        expected = connection.execute("SELECT count(*),sum(aptos) FROM read_parquet(?) WHERE tem_bu",[str(target)]).fetchone()
        assert (report["secoes_alvo"],report["aptos_alvo"]) == expected
        assert connection.execute("SELECT count(*) FROM pareado WHERE NOT tem_bu OR local_votacao IS NULL").fetchone()[0] == 0
        assert connection.execute("SELECT count(*)-count(DISTINCT (uf,cod_municipio,zona,secao)) FROM pareado").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM pareado WHERE pct_A_base NOT BETWEEN 0 AND 1 OR comparec_base NOT BETWEEN 0 AND 1 OR pareada<>(nivel_pareamento='secao')").fetchone()[0] == 0
