"""Exporta imagens do carrossel sem sobrescrever as figuras do README."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from apuracao.download import ROOT, read_json, write_json
from apuracao.plots import BLUE, GRAY, display_pct, principal


def exclusion_milestones(model: pl.DataFrame) -> dict[str, int | None]:
    """Distingue primeira exclusão do empate e exclusão contínua até o último corte."""
    rows = model.sort("marco").to_dicts()
    outside = [row["ic_lo_bruto"] > 50 or row["ic_hi_bruto"] < 50 for row in rows]
    first = next((row["marco"] for row, flag in zip(rows, outside) if flag), None)
    stable = next((row["marco"] for i, row in enumerate(rows) if all(outside[i:])), None)
    return {"primeira_exclusao": first, "exclusao_continua": stable}


def canvas(kicker: str, title: str, subtitle: str) -> Any:
    """Prepara uma página de 1080×1350 com a paleta das figuras principais."""
    fig = plt.figure(figsize=(7.2, 9), dpi=150, facecolor="#FAFBFD")
    fig.text(.10, .952, kicker, fontsize=10.2, color=GRAY, weight="bold")
    fig.text(.10, .90, title, fontsize=20, weight="bold", color="#243547", va="top", linespacing=1.25)
    fig.text(.10, .755, subtitle, fontsize=11, color=GRAY, va="top", linespacing=1.5)
    return fig


def save(fig: Any, name: str, root: Path) -> Path:
    """Salva uma página sem recorte que altere as dimensões solicitadas."""
    path = root / "reports" / "figures" / "linkedin" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def partial_2022(data: pl.DataFrame, root: Path) -> Path:
    """Mostra a parcial de 2022 e os cortes de 1% a 67% com liderança incorreta."""
    part = data.filter((pl.col("ano") == 2022) & (pl.col("modelo") == "M0")).sort("marco")
    wrong = part.filter(pl.col("previsto") < 50)["marco"].to_list()
    if wrong != list(range(1, 68)):
        raise ValueError("Os dados não sustentam a sombra de 1% a 67%")
    fig = canvas("2022  /  PARCIAL NA ORDEM DE RECEBIMENTO",
                 "Em 2022, a parcial mostrou\no líder errado por 2/3\nda apuração",
                 "Na ordem em que os boletins chegaram ao TSE")
    ax = fig.add_axes([.12, .27, .82, .40], facecolor="white")
    ax.axvspan(1, 67, color=GRAY, alpha=.12)
    ax.plot(part["pct_apurado"].to_numpy()*100, part["previsto"].to_numpy(), color=GRAY, lw=2.4, label="M0 · parcial")
    ax.axhline(50, color=BLUE, ls=":", lw=1.5, label="50% · empate")
    final = part["real"][0]
    ax.axhline(final, color="#36424D", ls="--", lw=1.2, label=f"Final · {display_pct(final)}%")
    ax.set(xlim=(0, 100), xlabel="Seções com BU recebidas (%)", ylabel="Candidato 13 nos válidos (%)")
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.grid(axis="y", alpha=.18)
    ax.legend(loc="upper left", bbox_to_anchor=(-.015, -.17), fontsize=10, frameon=False)
    fig.text(.10, .11, "Sombra: líder incorreto nos cortes de 1% a 67%.", fontsize=10, color=GRAY)
    fig.text(.10, .065, "Cortes de 1% a 99%. Fonte: TSE.", fontsize=9, color=GRAY)
    return save(fig, "parcial_2022_li.png", root)


def validation_rows(root: Path) -> list[list[str]]:
    """Confronta os totais dos Parquets com a fonte oficial independente do BU."""
    official = read_json(root / "data" / "raw" / "oficial" / "2026" / "totais.json")
    cols = ["votos_A", "votos_B", "votos_validos", "brancos", "nulos", "aptos"]
    ours = pl.scan_parquet(root / "data" / "interim" / "secoes_2026.parquet").select(
        [pl.col(col).sum() for col in cols]).collect().row(0)
    theirs = [official["candidatos"]["13"], official["candidatos"]["22"]] + [
        official["totais"][col] for col in cols[2:]]
    labels = ["Votos 13", "Votos 22", "Válidos", "Brancos", "Nulos", "Aptos"]
    rows = []
    for label, our, their in zip(labels, ours, theirs):
        if our != their:
            raise ValueError(f"Total divergente: {label}: {our} vs {their}")
        rows.append([label, f"{our:,}".replace(",", "."), f"{their:,}".replace(",", "."), "0"])
    return rows


def validation(root: Path) -> Path:
    """Desenha a validação com diferenças calculadas e igualdade exata obrigatória."""
    rows = validation_rows(root)
    fig = canvas("2026  /  VALIDAÇÃO DOS DADOS", "Nosso total = TSE", "Seis totais conferidos. Diferença zero.")
    ax = fig.add_axes([.065, .30, .87, .37])
    ax.axis("off")
    table = ax.table(cellText=rows, colLabels=["Indicador", "Nosso total", "TSE", "Diferença"],
                     colWidths=[.22, .285, .285, .21], cellLoc="right", bbox=[0, 0, 1, 1])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#FAFBFD")
        cell.set_linewidth(2)
        cell.set_facecolor("#E9EFF4" if r == 0 else ("white" if r % 2 else "#F0F3F6"))
        cell.set_text_props(color=BLUE if c == 3 and r else "#243547", weight="bold" if r == 0 or c == 3 else "normal")
        if c == 0:
            cell.set_text_props(ha="left")
    fig.text(.10, .225, "Inclui votos no exterior e o eleitorado\ndas seções sem boletim.", fontsize=11, color=GRAY, linespacing=1.5)
    fig.text(.10, .12, "Fonte independente dos boletins de urna:", fontsize=10, weight="bold", color=GRAY)
    fig.text(.10, .078, "TSE · votação por candidato/município/zona\ne detalhe da apuração. Detalhes no repositório.", fontsize=9.5, color=GRAY, linespacing=1.5)
    return save(fig, "validacao_li.png", root)


def error_bars(data: pl.DataFrame, root: Path) -> Path:
    """Compara erros absolutos em três cortes do teste de 2026."""
    fig = canvas("2026  /  TESTE FORA DA AMOSTRA", "Quanto a projeção errou?", "Erro absoluto em pontos percentuais\nMenor é melhor")
    ax = fig.add_axes([.12, .28, .82, .39], facecolor="white")
    x = np.arange(3)
    for name, offset, color, label in [("M0", -.19, GRAY, "M0 · parcial"), ("M3", .19, BLUE, "M3 · modelo")]:
        part = data.filter((pl.col("ano") == 2026) & (pl.col("modelo") == name) & pl.col("marco").is_in([10, 30, 50])).sort("marco")
        if part["marco"].to_list() != [10, 30, 50]:
            raise ValueError("Cortes de erro incompletos")
        heights = part["erro_pp"].abs().to_numpy()
        bars = ax.bar(x+offset, heights, width=.34, color=color, label=label)
        ax.bar_label(bars, labels=[display_pct(v) for v in heights], padding=6, fontsize=11, color=color, weight="bold")
    ax.set_xticks(x, ["10%", "30%", "50%"])
    ax.set(xlabel="Seções com BU recebidas", ylabel="Erro absoluto (p.p.)", ylim=(0, None))
    ax.set_ylim(0, ax.get_ylim()[1]*1.13)
    ax.grid(axis="y", alpha=.18)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", bbox_to_anchor=(-.015, -.17), ncol=2, fontsize=10, frameon=False)
    fig.text(.10, .12, "Na ordem em que os boletins chegaram ao TSE.", fontsize=10, color=GRAY)
    fig.text(.10, .075, "Previsões originais preservadas. Fonte: TSE.", fontsize=9.5, color=GRAY)
    return save(fig, "erro_li.png", root)


def generate_linkedin(root: Path = ROOT) -> list[Path]:
    """Gera cinco PNGs e confere a integridade das figuras e avaliações originais."""
    protected = list((root / "reports" / "figures").glob("*.png")) + [
        root / "data" / "processed" / "avaliacao.parquet", root / "docs" / "CALIBRACAO_IC.json",
        root / "docs" / "CALIBRACAO_K.json"]
    before = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    data = pl.read_parquet(root / "data" / "processed" / "avaliacao.parquet")
    milestones = {str(year): exclusion_milestones(data.filter((pl.col("ano") == year) & (pl.col("modelo") == "M3")))
                  for year in (2022, 2026)}
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False}):
        paths = [principal(year, root, linkedin=True, exclusion_marco=milestones[str(year)]["exclusao_continua"])
                 for year in (2026, 2022)]
        paths += [partial_2022(data, root), validation(root), error_bars(data, root)]
    if before != {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}:
        raise ValueError("Uma figura original ou avaliação foi alterada")
    write_json(root / "docs" / "LINKEDIN_FIGURAS.json", {
        "faixa": "Estrutural bruta, sem cobertura validada; escolha feita APÓS ver 2026.",
        "marcos_m3": milestones,
        "criterio": "Exclusão estrita: limite inferior > 50 ou superior < 50. Exclusão contínua até o último corte (99%).",
        "observacao": "Em 2022 exclui em 83%, volta a tocar em 84% e exclui continuamente desde 85%.",
        "validacao_2026": validation_rows(root), "arquivos_protegidos_sha256": before,
        "figuras": [str(p.relative_to(root)) for p in paths]})
    print("Marcos M3:", milestones)
    return paths


if __name__ == "__main__":
    generate_linkedin()
