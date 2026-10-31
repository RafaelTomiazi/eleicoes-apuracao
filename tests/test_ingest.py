"""Verifica agregação e confronta Parquets locais com totalização independente."""

import csv
from pathlib import Path

import duckdb
import pytest

from apuracao.config import CANDIDATES, OFFICIAL_TOTALS
from apuracao.download import ROOT, read_json
from apuracao.ingest import aggregate_csv


def write_fixture(path: Path, year: int, *, conflict: bool = False) -> None:
    """Gera BUs sintéticos com atributos repetidos e uma seção no exterior."""
    uf_column = "SG_ UF" if year == 2018 else "SG_UF"
    aggregate_column = "DS_SECOES_AGREGADAS" if year == 2026 else "DS_AGREGADAS"
    flash_column = "CD_FLASCARD_URNA_EFETIVADA" if year == 2018 else "CD_FLASHCARD_URNA_EFETIVADA"
    timestamp = "2026-10-25 17:10:00" if year == 2026 else "30/10/2022 17:10:00"
    rows = []
    for uf in ("AC","ZZ"):
        for number,kind,votes in [(13,"Nominal",30),(CANDIDATES[year]["B"],"Nominal",40),(95,"Branco",2),(96,"Nulo",8)]:
            row = {uf_column:uf,"CD_MUNICIPIO":"1007","NM_MUNICIPIO":"MUNICÍPIO",
                   "NR_ZONA":"1","NR_SECAO":"2","QT_APTOS":"100","QT_COMPARECIMENTO":"80",
                   "QT_ABSTENCOES":"20","NR_VOTAVEL":str(number),"DS_TIPO_VOTAVEL":kind,
                   "QT_VOTOS":str(votes),"CD_CARGO_PERGUNTA":"1","DS_CARGO_PERGUNTA":"Presidente",
                   "NR_TURNO":"2","ANO_ELEICAO":str(year),"DT_ENCERRAMENTO":timestamp,
                   aggregate_column:"3,4",flash_column:"ABCD"}
            if year != 2018:
                row.update(DT_BU_RECEBIDO=timestamp,DT_EMISSAO_BU=timestamp)
            rows.append(row)
    if conflict:
        rows[0]["QT_APTOS"] = "101"
    with path.open("w",encoding="latin-1",newline="") as output:
        writer = csv.DictWriter(output,fieldnames=list(rows[0]),delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize("year",[2018,2022,2026])
def test_repeated_attributes_votes_and_historical_headers(tmp_path: Path,year: int) -> None:
    """Deduplica eleitorado, soma votos e preserva agregadas e exterior."""
    source = tmp_path / "bu.csv"
    write_fixture(source,year)
    with duckdb.connect() as connection:
        connection.execute("INSTALL encodings")
        connection.execute("LOAD encodings")
        aggregate_csv(connection,source,year)
        assert connection.execute("SELECT count(*),sum(aptos),sum(comparecimento),sum(votos_A),sum(votos_B),sum(brancos),sum(nulos) FROM sections").fetchone() == (2,200,160,60,80,4,16)
        assert connection.execute("SELECT exterior,secoes_agregadas,cod_municipio,cd_flashcard_urna_efetivada FROM sections WHERE uf='ZZ'").fetchone() == (True,"3,4","01007","ABCD")
        assert connection.execute("SELECT count(*) FROM sections WHERE recebido_em_registrado IS NULL").fetchone()[0] == (2 if year == 2018 else 0)


def test_conflicting_repeated_attributes_fail(tmp_path: Path) -> None:
    """Recusa conflito em vez de esconder divergência sob max ou any_value."""
    source = tmp_path / "bu.csv"
    write_fixture(source,2022,conflict=True)
    with duckdb.connect() as connection:
        connection.execute("LOAD encodings")
        with pytest.raises(ValueError,match="divergentes"):
            aggregate_csv(connection,source,2022)


@pytest.mark.parametrize("year",[2018,2022,2026])
def test_real_parquet_against_independent_official_totals(year: int) -> None:
    """Exige igualdade exata dos votos e aptos com a fonte oficial externa ao BU."""
    path = ROOT / "data" / "interim" / f"secoes_{year}.parquet"
    official_path = ROOT / "data" / "raw" / "oficial" / str(year) / "totais.json"
    if not path.exists() or not official_path.exists():
        pytest.skip("Execute apuracao.ingest para obter os dados oficiais locais")
    official = read_json(official_path)
    with duckdb.connect() as connection:
        connection.execute("CREATE TEMP VIEW sections AS SELECT * FROM read_parquet('"+str(path).replace("'","''")+"')")
        aptos,a,b,validos = connection.execute("SELECT sum(aptos),sum(votos_A),sum(votos_B),sum(votos_validos) FROM sections").fetchone()
        assert aptos == official["totais"]["aptos"] == OFFICIAL_TOTALS[year]["aptos"]
        assert a == official["candidatos"][str(CANDIDATES[year]["A"]) ] == OFFICIAL_TOTALS[year]["votos_A"]
        assert b == official["candidatos"][str(CANDIDATES[year]["B"]) ] == OFFICIAL_TOTALS[year]["votos_B"]
        assert validos == official["totais"]["votos_validos"] == a+b
        expected_pct = 100*official["candidatos"][str(CANDIDATES[year]["A"]) ]/official["totais"]["votos_validos"]
        assert abs(100*a/validos-expected_pct) < 0.01
        assert connection.execute("SELECT count(*)-count(DISTINCT (uf,cod_municipio,zona,secao)) FROM sections").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM sections WHERE exterior<>(uf='ZZ') OR apta_simulacao<>tem_bu").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM sections WHERE NOT tem_bu AND (comparecimento<>0 OR votos_validos<>0 OR recebido_em IS NOT NULL)").fetchone()[0] == 0
        if year != 2018:
            assert connection.execute("SELECT count(*) FROM sections WHERE tem_bu AND (recebido_em IS NULL OR timezone('America/Sao_Paulo',recebido_em)<>recebido_em_registrado)").fetchone()[0] == 0
