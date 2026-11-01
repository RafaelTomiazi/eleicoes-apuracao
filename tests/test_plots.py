"""Confere a marcação do líder e as dimensões dos artefatos exportados."""

import polars as pl
import pytest
from PIL import Image

from apuracao.download import ROOT,read_json
from apuracao.plots import wrong_leader_spans
from apuracao.linkedin import exclusion_milestones


def test_exclusion_distinguishes_first_crossing_from_permanent_crossing() -> None:
    """Não confunde uma exclusão temporária nem um limite igual a 50 com exclusão contínua."""
    frame = pl.DataFrame({"marco": [82, 83, 84, 85, 86],
                          "ic_lo_bruto": [49.8, 50.001, 50., 50.1, 50.2],
                          "ic_hi_bruto": [52.] * 5})
    assert exclusion_milestones(frame) == {"primeira_exclusao": 83, "exclusao_continua": 85}


def test_band_touching_fifty_never_excludes_a_tie() -> None:
    """Considera 50% dentro da faixa inclusive quando coincide com um limite."""
    frame = pl.DataFrame({"marco": [1, 2], "ic_lo_bruto": [49., 50.], "ic_hi_bruto": [50., 51.]})
    assert exclusion_milestones(frame) == {"primeira_exclusao": None, "exclusao_continua": None}


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
