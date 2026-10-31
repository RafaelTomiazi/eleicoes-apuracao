"""Valida ordenação, conservação do universo e fechamento das parciais."""

from datetime import datetime, timezone

import polars as pl
import pytest

from apuracao.config import OFFICIAL_TOTALS
from apuracao.download import ROOT
from apuracao.simulate import (
    cut_points, ordered_sections, partial_table, snapshots, snapshots_from_ordered,
    summarize_partial,
)


def sample_sections() -> pl.DataFrame:
    """Cria cinco BUs fora de ordem e uma seção sem boletim."""
    return pl.DataFrame({
        "uf":["SP","RJ","ZZ","AC","SP","MT"],
        "cod_municipio":["00001","00002","99999","00003","00001","00004"],
        "zona":[1,1,1,1,1,1], "secao":[10,1,1,1,2,1],
        "recebido_em":[datetime(2022,10,30,hour,tzinfo=timezone.utc)
                       if hour is not None else None for hour in [20,21,14,22,20,None]],
        "tem_bu":[True,True,True,True,True,False],
        "votos_13":[20,30,0,10,40,0], "votos_validos":[50,100,0,50,50,0],
    })


def test_tied_times_use_numeric_section_order_and_are_reproducible() -> None:
    """Ordena empates pela chave, independentemente da ordem física do arquivo."""
    first = ordered_sections(sample_sections())
    second = ordered_sections(sample_sections().reverse())
    assert first.equals(second)
    assert first.select("uf","secao").rows() == [("ZZ",1),("SP",2),("SP",10),("RJ",1),("AC",1)]
    assert first["recebido_em"][0].hour == 11
    assert first["recebido_em"][0].utcoffset().total_seconds() == -10800


def test_snapshots_are_nested_complete_and_share_value_buffers() -> None:
    """Garante que nenhuma seção sai da parcial e que os slices não copiam valores."""
    ordered = ordered_sections(sample_sections())
    original_buffer = ordered["votos_13"].to_arrow().buffers()[1].address
    previous = set()
    for snapshot in snapshots_from_ordered(ordered,0.2):
        received = set(snapshot.apuradas["ordem_apuracao"])
        remaining = set(snapshot.faltantes["ordem_apuracao"])
        assert previous <= received
        assert received.isdisjoint(remaining)
        assert received | remaining == set(range(1,6))
        assert snapshot.apuradas.height+snapshot.faltantes.height == 5
        assert snapshot.pct_apurado == snapshot.apuradas.height/5
        assert snapshot.horario_corte == snapshot.apuradas["recebido_em"][-1]
        assert snapshot.apuradas["votos_13"].to_arrow().buffers()[1].address == original_buffer
        previous = received
    assert snapshot.pct_apurado == 1
    assert snapshot.faltantes.is_empty()


def test_partial_votes_and_regional_denominators() -> None:
    """Confere somas acumuladas e cobertura dentro de cada região."""
    partial = partial_table(ordered_sections(sample_sections()),0.2)
    assert partial["pct_13_parcial"].to_list() == [None,80,60,45,40]
    assert partial["pct_13_final"].to_list() == [40]*5
    assert partial["diferenca_pp"].to_list() == [None,40,20,5,0]
    assert partial["pct_apurado_SE"].to_list() == pytest.approx([0,1/3,2/3,1,1])
    assert partial["pct_apurado_N"].to_list() == [0,0,0,0,1]
    assert partial["pct_apurado_exterior"].to_list() == [1]*5
    assert partial["pct_apurado_CO"].to_list() == [None]*5


def test_cut_rounding_small_universe_and_final_inclusion() -> None:
    """Evita marcos duplicados e erros de ponto flutuante na contagem de seções."""
    assert cut_points(11,0.3) == [4,7,10,11]
    assert cut_points(3,0.01) == [1,2,3]
    assert cut_points(100,0.01) == list(range(1,101))
    assert cut_points(499205,0.01)[29] == 149762
    assert cut_points(499205,1) == [499205]


@pytest.mark.parametrize("step",[0,-0.1,1.1,float("nan"),float("inf")])
def test_invalid_steps_are_rejected(step: float) -> None:
    """Recusa passos que impediriam um avanço finito até 100%."""
    with pytest.raises(ValueError,match="passo"):
        cut_points(10,step)


def test_missing_time_does_not_get_a_simulated_order() -> None:
    """Recusa BU sem horário em vez de inventar uma posição na fila."""
    sample = sample_sections().with_columns(pl.lit(None,dtype=pl.Datetime("us","UTC")).alias("recebido_em"))
    with pytest.raises(ValueError,match="horário nulo"):
        ordered_sections(sample)


def test_first_crossing_is_distinct_from_sustained_convergence() -> None:
    """Distingue um acerto inicial de permanecer abaixo do limite até o fim."""
    partial = pl.DataFrame({"pct_apurado":[0.1,0.2,0.3,0.4,1.0],
                            "diferenca_pp":[0.5,1.2,0.2,1.0,0.0],
                            "n_apuradas":[1,2,3,4,10],"pct_13_final":[50.0]*5})
    report = summarize_partial(partial,2022)
    assert report["primeiro_abaixo_1pp"] == 0.1
    assert report["abaixo_1pp_ate_final"] == 1
    assert report["maior_desvio_absoluto_pp"] == 1.2
    assert report["pct_apurado_maior_desvio"] == 0.2


@pytest.mark.parametrize("year",[2022,2026])
def test_real_snapshots_and_official_final(year: int) -> None:
    """Verifica os cem snapshots reais e o resultado final oficial independente."""
    source = ROOT / "data" / "processed" / f"pareado_{year}.parquet"
    partial_path = ROOT / "data" / "processed" / f"parcial_{year}.parquet"
    if not source.exists() or not partial_path.exists():
        pytest.skip("Execute apuracao.match e apuracao.simulate para os dados reais")
    partial = pl.read_parquet(partial_path)
    assert partial.height == 100
    assert partial["pct_apurado"].is_sorted()
    assert partial["horario_corte"].is_sorted()
    official = OFFICIAL_TOTALS[year]
    expected_pct = 100*official["votos_A"]/official["votos_validos"]
    assert partial["pct_13_parcial"][-1] == pytest.approx(expected_pct,abs=1e-12)
    assert partial["diferenca_pp"][-1] == 0
    previous_count = 0
    total = None
    for snapshot in snapshots(year):
        assert snapshot.apuradas.height > previous_count
        current_total = snapshot.apuradas.height+snapshot.faltantes.height
        total = current_total if total is None else total
        assert current_total == total
        assert snapshot.apuradas["ordem_apuracao"][0] == 1
        assert snapshot.apuradas["ordem_apuracao"][-1] == snapshot.apuradas.height
        if snapshot.faltantes.height:
            assert snapshot.faltantes["ordem_apuracao"][0] == snapshot.apuradas.height+1
        previous_count = snapshot.apuradas.height
    assert snapshot.pct_apurado == 1
    assert snapshot.faltantes.is_empty()
    assert snapshot.apuradas["votos_13"].sum() == official["votos_A"]
    assert snapshot.apuradas["votos_validos"].sum() == official["votos_validos"]
