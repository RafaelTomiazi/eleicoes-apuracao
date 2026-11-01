"""Confere a marcação do líder e as dimensões dos artefatos exportados."""

import polars as pl
import pytest
from PIL import Image

from apuracao.download import ROOT,read_json
from apuracao.plots import wrong_leader_spans


def test_tie_is_not_labeled_as_the_wrong_leader() -> None:
    """Uma parcial empatada não aponta o candidato perdedor como líder."""
    frame = pl.DataFrame({"pct_apurado":[.01,.02,.03,.04],"previsto":[49.,49.,50.,51.],"real":[51.]*4})
    assert wrong_leader_spans(frame) == [(0.,3.)]


@pytest.mark.parametrize("year",[2022,2026])
def test_portrait_export_dimensions_and_posthoc_disclosure(year: int) -> None:
    """Exige tamanho solicitado e declaração de escolha posterior ao teste."""
    path = ROOT / "reports" / "figures" / f"projecao_{year}.png"
    if not path.exists():
        pytest.skip("Execute apuracao.plots")
    with Image.open(path) as figure:
        assert figure.size == (1080,1350)
    audit = read_json(ROOT / "docs" / "FIGURAS_AUDITORIA.json")
    assert "APÓS" in audit["escolha"]
    assert "sem cobertura nominal validada" in audit["faixa"]
