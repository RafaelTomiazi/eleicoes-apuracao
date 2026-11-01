"""Confere a atribuição do erro e a preservação do teste fora da amostra."""

import numpy as np
import pytest

from apuracao.bias import fingerprint, oracle_decomposition
from apuracao.download import ROOT,read_json


def test_share_error_is_not_attributed_to_turnout_or_invalid_votes() -> None:
    """Um erro exclusivamente na participação deve pertencer somente ao swing."""
    predicted = np.array([[.6,1,0],[.6,1,0]])
    truth = np.array([[.5,1,0],[.5,1,0]])
    result = oracle_decomposition(predicted,truth,np.array([100,100]),np.array([False,False]),50,100,50)
    assert result["erro_pp"] == pytest.approx(100*170/300-50)
    assert result["contribuicoes_shapley_pp"]["swing"] == pytest.approx(result["erro_pp"])
    for key in ("comparecimento","brancos_nulos","exterior"):
        assert result["contribuicoes_shapley_pp"][key] == pytest.approx(0)


def test_exterior_is_a_separate_block_without_double_counting() -> None:
    """O erro de ZZ não deve reaparecer nas três parcelas domésticas."""
    predicted = np.array([[.5,1,0],[.9,1,0]])
    truth = np.array([[.5,1,0],[.1,1,0]])
    result = oracle_decomposition(predicted,truth,np.array([100,100]),np.array([False,True]),50,100,100*110/300)
    assert result["contribuicoes_shapley_pp"]["exterior"] == pytest.approx(result["erro_pp"])
    for key in ("comparecimento","brancos_nulos","swing"):
        assert result["contribuicoes_shapley_pp"][key] == pytest.approx(0)


def test_interactions_reconcile_and_do_not_depend_on_section_order() -> None:
    """Atribui interações sem deixar resíduo e sem escolher uma ordem causal."""
    predicted = np.array([[.7,.8,.1],[.4,.9,.2]])
    truth = np.array([[.6,.9,.15],[.3,.7,.1]])
    aptos = np.array([100,200])
    valid = aptos*truth[:,1]*(1-truth[:,2])
    final = 100*(50+(valid*truth[:,0]).sum())/(100+valid.sum())
    result = oracle_decomposition(predicted,truth,aptos,np.array([False,True]),50,100,final)
    reverse = oracle_decomposition(predicted[::-1],truth[::-1],aptos[::-1],np.array([True,False]),50,100,final)
    assert sum(result["contribuicoes_shapley_pp"].values()) == pytest.approx(result["erro_pp"])
    assert result["erro_todas_taxas_reais_pp"] == pytest.approx(0)
    assert result["contribuicoes_shapley_pp"] == pytest.approx(reverse["contribuicoes_shapley_pp"])


def test_real_diagnosis_preserves_evaluation_and_calibrations() -> None:
    """Impede que o diagnóstico retifique os números do teste original."""
    path = ROOT / "docs" / "DIAGNOSTICO_VIES.json"
    if not path.exists():
        pytest.skip("Execute apuracao.bias para gerar o diagnóstico real")
    report = read_json(path)
    if not (ROOT / "data" / "processed" / "avaliacao.parquet").exists():
        pytest.skip("Dados locais ausentes")
    for name,expected in report["arquivos_protegidos_sha256"].items():
        assert fingerprint(ROOT / name)==expected
    for row in report["cortes_30"]:
        assert sum(row["contribuicoes_shapley_pp"].values()) == pytest.approx(row["erro_pp"],abs=1e-10)
