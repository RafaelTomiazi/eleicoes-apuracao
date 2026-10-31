"""Verifica recuperação de swing e ausência de acesso aos resultados futuros."""

from dataclasses import replace
from datetime import date, datetime, timezone

import numpy as np
import polars as pl
import pytest

from apuracao.config import OFFICIAL_TOTALS
from apuracao.download import ROOT
from apuracao.models import KNOWN, M0, M1, M2, M3, Previsao
from apuracao.simulate import Snapshot


def synthetic_snapshot(*, uniform: bool = False) -> Snapshot:
    """Cria municípios com swings conhecidos e cobertura desigual."""
    records = []
    for municipality,count in (("00001",60),("00002",30)):
        base = 0.3 if municipality=="00001" else 0.6
        swing = 0.05 if uniform else (0.15 if municipality=="00001" else -0.1)
        for section in range(count):
            records.append({"uf":"SP","cod_municipio":municipality,"secao":section,
                            "aptos":2000,"comparecimento":1800,"votos_validos":1440,
                            "votos_13":1440*(base+swing),"pct_A_base":base,
                            "comparec_base":0.8,"bn_base":0.1,"apurada":section<20})
    frame = pl.DataFrame(records)
    return Snapshot(40/90,datetime(2022,10,30,20,tzinfo=timezone.utc),
                    frame.filter(pl.col("apurada")),frame.filter(~pl.col("apurada")))


def indicators(published: date = date(2021,12,17)) -> pl.DataFrame:
    """Fornece indicadores sintéticos com data de publicação explícita."""
    return pl.DataFrame({"uf":["SP","SP"],"cod_municipio":["00001","00002"],
                         "ibge_pop_2021":[10000.,20000.],"ibge_pib_per_capita_2019":[15000.,25000.],
                         "ibge_publicado_em":[published,published]})


def final_percentage(snapshot: Snapshot) -> float:
    """Calcula a verdade sintética apenas para conferir o teste."""
    frame = pl.concat([snapshot.apuradas,snapshot.faltantes])
    return 100*frame["votos_13"].sum()/frame["votos_validos"].sum()


def test_uniform_swing_and_turnout_invalid_vote_rates() -> None:
    """M1 recupera o swing uniforme das três taxas e combina os votos válidos."""
    snapshot = synthetic_snapshot(uniform=True)
    prediction = M1(n_bootstrap=20).prever(snapshot)
    assert prediction.pct_13 == pytest.approx(final_percentage(snapshot))
    assert prediction.ic_lo == pytest.approx(prediction.pct_13)
    assert prediction.ic_hi == pytest.approx(prediction.pct_13)


def test_municipal_swing_is_recovered_without_shrinkage() -> None:
    """M2 com k=0 recupera municípios com swings diferentes e tamanhos desiguais."""
    snapshot = synthetic_snapshot()
    expected = final_percentage(snapshot)
    prediction = M2(k=0,n_bootstrap=20).prever(snapshot)
    assert prediction.pct_13 == pytest.approx(expected)
    assert abs(M1(n_bootstrap=0).prever(snapshot).pct_13-expected)>1
    assert abs(M2(k=20,n_bootstrap=0).prever(snapshot).pct_13-expected)>0


@pytest.mark.parametrize("model",[M0,M1,M2,M3])
def test_future_votes_zeroed_and_future_results_removed_do_not_change_forecast(model: type) -> None:
    """Impede cola mesmo quando todas as colunas de resultados futuros somem."""
    snapshot = synthetic_snapshot()
    instance = model(k=5,n_bootstrap=8,indicadores=indicators(),min_train=1)
    expected = instance.prever(snapshot)
    poisoned = snapshot.faltantes.with_columns(
        *[pl.lit(0).alias(column) for column in snapshot.faltantes.columns if column not in KNOWN])
    assert instance.prever(replace(snapshot,faltantes=poisoned)) == expected
    assert instance.prever(replace(snapshot,faltantes=snapshot.faltantes.select(KNOWN))) == expected


@pytest.mark.parametrize("model",[M0,M1,M2,M3])
def test_all_models_collapse_to_actual_final_at_full_count(model: type) -> None:
    """Em 100%, nenhum modelo projeta ou acrescenta incerteza artificial."""
    snapshot = synthetic_snapshot()
    full = pl.concat([snapshot.apuradas,snapshot.faltantes])
    complete = replace(snapshot,pct_apurado=1,apuradas=full,faltantes=full.head(0))
    expected = final_percentage(snapshot)
    assert model(n_bootstrap=20).prever(complete) == Previsao(expected,expected,expected)


def test_m3_fallback_is_exactly_m2_below_2000_sections() -> None:
    """M3 não treina árvores nem exige indicadores quando há poucas apuradas."""
    snapshot = synthetic_snapshot()
    assert M3(k=5,n_bootstrap=8).prever(snapshot) == M2(k=5,n_bootstrap=8).prever(snapshot)


def test_future_indicator_publication_is_rejected() -> None:
    """Recusa indicador divulgado depois da data do snapshot de 2022."""
    with pytest.raises(ValueError,match="publicado depois"):
        M3(indicadores=indicators(date(2023,1,1)),min_train=1,n_bootstrap=0).prever(synthetic_snapshot())


def test_bootstrap_does_not_retrain_lightgbm(monkeypatch: pytest.MonkeyPatch) -> None:
    """O bootstrap reutiliza os três ajustes, um para cada taxa."""
    from apuracao import models

    original_fit = models.LGBMRegressor.fit
    fit_rows = []

    def counted_fit(self: object, x: np.ndarray, y: np.ndarray, **kwargs: object) -> object:
        """Registra o tamanho do treino sem alterar o estimador."""
        fit_rows.append(len(x))
        return original_fit(self,x,y,**kwargs)

    monkeypatch.setattr(models.LGBMRegressor,"fit",counted_fit)
    snapshot = synthetic_snapshot()
    M3(indicadores=indicators(),min_train=1,n_bootstrap=12).prever(snapshot)
    assert fit_rows == [snapshot.apuradas.height]*3


@pytest.mark.parametrize("year",[2022,2026])
def test_real_full_count_matches_official_for_every_model(year: int) -> None:
    """Confere o fechamento real sem treinar nem executar outros snapshots."""
    path = ROOT / "data" / "processed" / f"pareado_{year}.parquet"
    if not path.exists():
        pytest.skip("Execute a ingestão e o pareamento reais")
    frame = pl.read_parquet(path)
    snapshot = Snapshot(1,datetime(year,10,31,tzinfo=timezone.utc),frame,frame.head(0))
    expected = 100*OFFICIAL_TOTALS[year]["votos_A"]/OFFICIAL_TOTALS[year]["votos_validos"]
    for cls in (M0,M1,M2,M3):
        assert cls().prever(snapshot).pct_13 == pytest.approx(expected,abs=1e-12)
