"""Verifica calibração exclusiva em 2022 e resumo de estabilidade do vencedor."""

import math
import hashlib

import polars as pl

import pytest

from apuracao.evaluate import apply_ic_calibration, calibrate_intervals, final_rows, progress_band, winner_stability
from apuracao.models import Previsao
from apuracao.download import ROOT, read_json


def calibration_rows() -> list[dict]:
    """Constrói faixas completas com escores conhecidos e verdade fixa."""
    rows = []
    for model in ("M0","M1","M2","M3"):
        for mark in range(1,100):
            error = (mark-1)%10+1
            point = 50-error
            rows.append({"ano":2022,"modelo":model,"marco":mark,
                         "pct_apurado":(mark+0.0001)/100,"real":50.,"previsto":point,
                         "ic_lo_bruto":point-1,"ic_hi_bruto":point+1})
    return rows


def test_empirical_factors_achieve_calibration_target_by_fixed_band() -> None:
    """Escolhe o quantil mínimo que cobre pelo menos 90% em cada faixa."""
    rows = calibration_rows()
    calibration = calibrate_intervals(rows)
    final = final_rows(rows,calibration)
    for model in ("M1","M2","M3"):
        assert calibration["fatores"][model]["0"]["fator"] == 9
        for band in range(10):
            selected = [row for row in final if row["modelo"]==model and progress_band(row["pct_apurado"])==band]
            assert sum(row["cobriu"] for row in selected)>=math.ceil(0.9*len(selected))


def test_2026_cannot_enter_calibration_and_point_is_unchanged() -> None:
    """Mantém a separação entre desenvolvimento e teste fora da amostra."""
    with pytest.raises(ValueError,match="somente registros de 2022"):
        calibrate_intervals([{"ano":2026}])
    calibration = calibrate_intervals(calibration_rows())
    prediction = Previsao(52,51,53)
    adjusted = apply_ic_calibration(prediction,"M3",0.100001,calibration)
    assert adjusted == Previsao(52,43,61)
    assert prediction.pct_13 == adjusted.pct_13
    assert apply_ic_calibration(prediction,"M0",0.1,calibration) == prediction
    assert apply_ic_calibration(prediction,"M3",1,calibration) == prediction


def test_progress_band_respects_integer_section_rounding() -> None:
    """Não desloca o corte de 10% para a faixa seguinte por ceil das seções."""
    assert progress_band(0.100001)==0
    assert progress_band(0.110001)==1
    assert progress_band(0.990001)==9


def test_winner_stability_is_retrospective_and_reports_wrong_stable_leader() -> None:
    """Distingue estabilizar o líder de estabilizar o vencedor correto."""
    rows = [{"marco":mark,"pct_apurado":mark/100,"previsto":point,"real":51}
            for mark,point in ((10,48),(20,51),(30,49),(40,51),(50,52))]
    assert winner_stability(rows) == {"lider_em_99":13,"estavel_desde":0.4,"marco_estavel":40,"confere_final":True}
    wrong = [row | {"previsto":49} for row in rows]
    assert winner_stability(wrong)["confere_final"] is False


def test_complete_local_evaluation_has_full_grid_and_frozen_calibration() -> None:
    """Audita o artefato final sem executar novamente as centenas de previsões."""
    path = ROOT / "data" / "processed" / "avaliacao.parquet"
    metadata = ROOT / "docs" / "AVALIACAO_EXECUCAO.json"
    if not path.exists() or not metadata.exists():
        pytest.skip("Execute apuracao.evaluate para produzir a avaliação completa")
    frame = pl.read_parquet(path)
    assert frame.height == 792
    assert frame.select("ano","modelo","marco").is_duplicated().any() is False
    assert set(frame["ano"].unique()) == {2022,2026}
    for group in frame.partition_by(["ano","modelo"]):
        assert sorted(group["marco"].to_list()) == list(range(1,100))
        if group["ano"][0]==2022 and group["modelo"][0]!="M0":
            assert group["cobriu"].mean()>=0.9
    assert frame.schema["cobriu"] == pl.Boolean
    assert frame.schema["horario_corte"].time_zone is not None
    calibration = ROOT / "docs" / "CALIBRACAO_IC.json"
    assert read_json(calibration)["ano_calibracao"]==2022
    assert hashlib.sha256(calibration.read_bytes()).hexdigest()==read_json(metadata)["calibracao_sha256"]
    # A correção deve alterar a incerteza, mantendo os pontos do Prompt 5.
    for previous in read_json(ROOT / "docs" / "BENCHMARK_MODELOS.json"):
        actual = frame.filter((pl.col("ano")==previous["ano"]) &
                              (pl.col("modelo")==previous["modelo"]) &
                              (pl.col("marco")==previous["marco"]))["previsto"].item()
        assert actual == pytest.approx(previous["previsto"],abs=1e-8)
