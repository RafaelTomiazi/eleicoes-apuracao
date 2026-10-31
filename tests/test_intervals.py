"""Regressão para incerteza comum que não pode se cancelar entre municípios."""

from datetime import datetime, timezone

import polars as pl

from apuracao.models import M1
from apuracao.simulate import Snapshot


def test_common_uf_uncertainty_does_not_vanish_with_many_municipalities() -> None:
    """Muitas faltantes da mesma UF devem compartilhar o choque estrutural."""
    observed = pl.DataFrame([
        {"uf":uf,"cod_municipio":f"{i:05}","aptos":1000,"comparecimento":1000,
         "votos_validos":1000,"votos_13":votes,"pct_A_base":0.5,"comparec_base":1.0,"bn_base":0.0}
        for uf,votes in (("SP",600),("RJ",400)) for i in range(20)
    ])
    missing = pl.DataFrame([
        {"uf":"SP","cod_municipio":f"{i:05}","aptos":1000,
         "pct_A_base":0.5,"comparec_base":1.0,"bn_base":0.0} for i in range(4000)
    ])
    snapshot = Snapshot(40/4040,datetime(2022,10,30,tzinfo=timezone.utc),observed,missing)
    prediction = M1(n_bootstrap=100,calibrar_ic=False).prever(snapshot)
    assert prediction.ic_hi-prediction.ic_lo>8, "Choques comuns não podem desaparecer por média entre municípios"
    assert abs((prediction.ic_hi-prediction.pct_13)-(prediction.pct_13-prediction.ic_lo))<1e-10
