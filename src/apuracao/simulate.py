"""Reconstrói a sequência de recebimento e as parciais presidenciais."""

from __future__ import annotations

import argparse
import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any

import polars as pl

from apuracao.config import OFFICIAL_TOTALS
from apuracao.download import ROOT, ensure_directories, read_json, write_json

KEYS = ["uf", "cod_municipio", "zona", "secao"]
REGIONS = {
    **dict.fromkeys("AC AP AM PA RO RR TO".split(), "N"),
    **dict.fromkeys("AL BA CE MA PB PE PI RN SE".split(), "NE"),
    **dict.fromkeys("DF GO MT MS".split(), "CO"),
    **dict.fromkeys("ES MG RJ SP".split(), "SE"),
    **dict.fromkeys("PR RS SC".split(), "S"),
    "ZZ": "exterior",
}
REGION_ORDER = ("N", "NE", "CO", "SE", "S", "exterior")


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Representa um corte da apuração com fração efetiva de seções recebidas."""

    pct_apurado: float
    horario_corte: datetime
    apuradas: pl.DataFrame
    faltantes: pl.DataFrame


def cut_points(total: int, passo: float = 0.01) -> list[int]:
    """Arredonda os marcos para cima e inclui o corte final sem repetições."""
    if not math.isfinite(passo) or not 0 < passo <= 1:
        raise ValueError("passo deve ser finito e estar entre 0 (exclusivo) e 1")
    if total <= 0:
        raise ValueError("Universo sem seções com BU")
    step = Decimal(str(passo))
    cuts = []
    previous = 0
    # Para universos pequenos, pular marcos que não acrescentariam uma seção.
    while previous < total:
        next_step = (Decimal(previous) / (Decimal(total) * step)).to_integral_value(rounding="ROUND_FLOOR") + 1
        fraction = min(next_step * step, Decimal(1))
        count = int((fraction * total).to_integral_value(rounding=ROUND_CEILING))
        if count <= previous:
            raise ValueError("passo sem avanço numérico representável")
        cuts.append(count)
        previous = count
    return cuts


def ordered_sections(frame: pl.DataFrame) -> pl.DataFrame:
    """Seleciona os BUs, valida as chaves e ordena uma única vez em Brasília."""
    required = {*KEYS, "tem_bu", "recebido_em", "votos_13", "votos_validos"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Colunas ausentes no pareamento: {sorted(missing)}")
    frame = frame.filter(pl.col("tem_bu"))
    if not frame.height:
        raise ValueError("Universo sem seções com BU")
    if frame.select([*KEYS, "recebido_em"]).null_count().sum_horizontal().item():
        raise ValueError("BU com chave ou horário nulo; revisar ingestão")
    if frame.select(KEYS).is_duplicated().any():
        raise ValueError("Chave de seção duplicada no universo")
    time_type = frame.schema["recebido_em"]
    if not isinstance(time_type, pl.Datetime) or time_type.time_zone is None:
        raise ValueError("recebido_em precisa informar fuso horário")
    if not set(frame["uf"].unique().to_list()) <= set(REGIONS):
        raise ValueError("UF sem região conhecida")
    if "ordem_apuracao" in frame.columns:
        raise ValueError("Coluna ordem_apuracao já existe na entrada")
    return (
        frame.with_columns(
            pl.col("recebido_em").dt.convert_time_zone("America/Sao_Paulo"),
            pl.col("uf").replace_strict(REGIONS).alias("regiao"),
        )
        .sort(["recebido_em", *KEYS])
        .with_row_index("ordem_apuracao", offset=1)
    )


def snapshots_from_ordered(ordered: pl.DataFrame, passo: float = 0.01) -> Iterator[Snapshot]:
    """Produz slices que compartilham os buffers da tabela já ordenada."""
    total = ordered.height
    for count in cut_points(total, passo):
        yield Snapshot(
            pct_apurado=count / total,
            horario_corte=ordered["recebido_em"][count - 1],
            apuradas=ordered.slice(0, count),
            faltantes=ordered.slice(count, total - count),
        )


def snapshots(ano: int, passo: float = 0.01) -> Iterator[Snapshot]:
    """Lê o pareamento uma vez e fornece os cortes da apuração do ano."""
    if ano not in (2022, 2026):
        raise ValueError("A simulação com horários de BU suporta 2022 e 2026")
    path = ROOT / "data" / "processed" / f"pareado_{ano}.parquet"
    ordered = ordered_sections(pl.read_parquet(path))
    yield from snapshots_from_ordered(ordered, passo)


def partial_table(ordered: pl.DataFrame, passo: float = 0.01) -> pl.DataFrame:
    """Calcula parciais com somas acumuladas e seleciona somente os cortes."""
    cuts = cut_points(ordered.height, passo)
    final_valid = ordered["votos_validos"].sum()
    if final_valid <= 0:
        raise ValueError("Universo sem votos válidos")
    final_pct = 100 * ordered["votos_13"].sum() / final_valid
    region_totals = dict(ordered.group_by("regiao").len().iter_rows())
    prefix = ordered.select(
        "recebido_em",
        pl.col("votos_13").cum_sum().alias("_votos_13"),
        pl.col("votos_validos").cum_sum().alias("_validos"),
        *[pl.col("regiao").eq(region).cast(pl.Int64).cum_sum().alias(f"_n_{region}")
          for region in REGION_ORDER],
    )
    selected = prefix[[count - 1 for count in cuts]].with_columns(pl.Series("n_apuradas", cuts))
    result = selected.select(
        (pl.col("n_apuradas") / ordered.height).alias("pct_apurado"),
        pl.col("recebido_em").alias("horario_corte"),
        pl.when(pl.col("_validos") > 0).then(100 * pl.col("_votos_13") / pl.col("_validos"))
          .otherwise(None).alias("pct_13_parcial"),
        pl.lit(final_pct).alias("pct_13_final"),
        "n_apuradas",
        (ordered.height - pl.col("n_apuradas")).alias("n_faltantes"),
        *[(pl.col(f"_n_{region}") / region_totals[region] if region_totals.get(region)
           else pl.lit(None, dtype=pl.Float64)).alias(f"pct_apurado_{region}") for region in REGION_ORDER],
    )
    return result.with_columns((pl.col("pct_13_parcial") - pl.col("pct_13_final")).alias("diferenca_pp"))


def summarize_partial(partial: pl.DataFrame, year: int) -> dict[str, Any]:
    """Resume o primeiro acerto, a convergência sustentada e o maior desvio."""
    rows = partial.select("pct_apurado", "diferenca_pp").to_dicts()
    inside = [row["diferenca_pp"] is not None and abs(row["diferenca_pp"]) < 1 for row in rows]
    first = next((row["pct_apurado"] for row, good in zip(rows, inside) if good), None)
    last_bad = max((i for i, good in enumerate(inside) if not good), default=-1)
    stable = rows[last_bad + 1]["pct_apurado"] if last_bad + 1 < len(rows) else None
    valid = [row for row in rows if row["diferenca_pp"] is not None]
    worst = max(valid, key=lambda row: abs(row["diferenca_pp"]))
    return {"ano": year, "snapshots": partial.height,
            "secoes_com_bu": partial["n_apuradas"][-1],
            "primeiro_abaixo_1pp": first, "abaixo_1pp_ate_final": stable,
            "maior_desvio_absoluto_pp": abs(worst["diferenca_pp"]),
            "desvio_com_sinal_pp": worst["diferenca_pp"],
            "pct_apurado_maior_desvio": worst["pct_apurado"],
            "pct_13_final": partial["pct_13_final"][-1]}


def plot_partial(partial: pl.DataFrame, year: int, path: Path) -> None:
    """Desenha a parcial do candidato 13 com cores neutras e referência final."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.subplots_adjust(left=0.12, right=0.98, bottom=0.18, top=0.90)
    x = partial["pct_apurado"].to_numpy() * 100
    ax.plot(x, partial["pct_13_parcial"].to_numpy(), color="#416B91", linewidth=2,
            label="Candidato 13 na parcial")
    ax.axhline(partial["pct_13_final"][-1], color="#636363", linestyle="--", linewidth=1.5,
               label="Candidato 13: resultado final oficial")
    ax.set(title=f"Parcial durante o recebimento dos boletins — {year}",
           xlabel="Seções com boletim recebidas (%)", ylabel="Candidato 13 (% dos votos válidos)",
           xlim=(0, 100))
    ax.grid(alpha=0.2)
    ax.legend(loc="best")
    fig.text(0.5, 0.035, "Fonte: TSE. Corte por seções com BU; empates desfeitos pela chave da seção.",
             ha="center", fontsize=9, color="#555555")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def document_simulation(root: Path = ROOT) -> None:
    """Versiona os indicadores observados e atualiza o trecho gerado do método."""
    reports = []
    for year in (2022, 2026):
        path = root / "data" / "processed" / f"resumo_parcial_{year}.json"
        if path.exists():
            reports.append(read_json(path))
    write_json(root / "docs" / "SIMULACAO_PARCIAL.json", reports)
    lines = ["## Parciais observadas na simulação (Prompt 4)", "",
             "Resultados nos marcos configurados (passo padrão de 1% das seções com BU), arredondados para cima. "
             "Os percentuais abaixo são as frações efetivamente recebidas, e não frações de votos.", "",
             "| Ano | Seções com BU | Primeiro corte com erro <1 p.p. | Abaixo de 1 p.p. até o final | Maior desvio absoluto | Corte do maior desvio |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for report in reports:
        first = f"{100*report['primeiro_abaixo_1pp']:.4f}%" if report["primeiro_abaixo_1pp"] is not None else "não atingido"
        stable = f"{100*report['abaixo_1pp_ate_final']:.4f}%" if report["abaixo_1pp_ate_final"] is not None else "não atingido"
        lines.append(f"| {report['ano']} | {report['secoes_com_bu']} | {first} | {stable} | {report['maior_desvio_absoluto_pp']:.4f} p.p. | {100*report['pct_apurado_maior_desvio']:.4f}% |")
    lines += ["", "O maior desvio acima é medido somente nos snapshots solicitados; "
              "não é o máximo a cada BU individual. Atingir <1 p.p. uma vez difere de "
              "permanecer nesse intervalo nos cortes seguintes. A parcial é descritiva, "
              "sem projeção das seções faltantes e sem intervalo de confiança.", ""]
    method = root / "docs" / "METODO.md"
    existing = method.read_text(encoding="utf-8") if method.exists() else "# Método\n"
    start, end = "<!-- inicio:simulacao-parcial -->", "<!-- fim:simulacao-parcial -->"
    block = start + "\n" + "\n".join(lines) + "\n" + end
    if start in existing and end in existing:
        before, rest = existing.split(start, 1)
        _, after = rest.split(end, 1)
        content = before + block + after
    else:
        content = existing.rstrip() + "\n\n" + block + "\n"
    method.write_text(content, encoding="utf-8")


def simulate_year(year: int, passo: float = 0.01, root: Path = ROOT) -> dict[str, Any]:
    """Gera a parcial e o gráfico após conferir o resultado final oficial."""
    if year not in (2022, 2026):
        raise ValueError("A simulação com horários de BU suporta 2022 e 2026")
    ensure_directories(root)
    ordered = ordered_sections(pl.read_parquet(root / "data" / "processed" / f"pareado_{year}.parquet"))
    official = OFFICIAL_TOTALS[year]
    if ordered["votos_13"].sum() != official["votos_A"] or ordered["votos_validos"].sum() != official["votos_validos"]:
        raise ValueError("Votos do universo divergem do resultado oficial; revisar ingestão/pareamento")
    partial = partial_table(ordered, passo)
    target = root / "data" / "processed" / f"parcial_{year}.parquet"
    temporary = target.with_suffix(".parquet.part")
    partial.write_parquet(temporary, compression="zstd")
    temporary.replace(target)
    report = summarize_partial(partial, year) | {"passo": passo}
    write_json(root / "data" / "processed" / f"resumo_parcial_{year}.json", report)
    plot_partial(partial, year, root / "reports" / "figures" / f"parcial_{year}.png")
    document_simulation(root)
    print(report, flush=True)
    return report


def main() -> None:
    """Executa a simulação de parciais de 2022 e 2026."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ano", type=int, choices=(2022, 2026), nargs="+", default=[2022, 2026])
    parser.add_argument("--passo", type=float, default=0.01)
    args = parser.parse_args()
    for year in args.ano:
        simulate_year(year, args.passo)


if __name__ == "__main__":
    main()
