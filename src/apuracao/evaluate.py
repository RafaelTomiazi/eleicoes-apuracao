"""Calibra os intervalos em 2022 e avalia os modelos no teste de 2026."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import polars as pl

from apuracao.config import OFFICIAL_TOTALS
from apuracao.download import ROOT, read_json, write_json
from apuracao.models import M0, M1, M2, M3, Previsao
from apuracao.simulate import Snapshot, cut_points, ordered_sections

MODEL_CLASSES = {cls.__name__:cls for cls in (M0,M1,M2,M3)}
_ORDERED: pl.DataFrame | None = None
_INDICATORS: pl.DataFrame | None = None
_CUTS: list[int] = []
_JOBS = 2


def progress_band(pct: float) -> int:
    """Identifica a faixa de dez marcos, preservando o arredondamento dos cortes."""
    mark = max(1,min(99,int(pct*100+1e-9)))
    return (mark-1)//10


def apply_ic_calibration(prediction: Previsao, model: str, pct: float,
                         calibration: dict[str, Any]) -> Previsao:
    """Aplica o fator congelado de 2022 sem consultar o resultado do ano alvo."""
    if model=="M0" or pct>=1:
        return prediction
    if calibration["ano_calibracao"]!=2022:
        raise ValueError("A calibração dos intervalos deve vir exclusivamente de 2022")
    factor = calibration["fatores"][model][str(progress_band(pct))]["fator"]
    return Previsao(prediction.pct_13,
                    max(0.,prediction.pct_13-factor*(prediction.pct_13-prediction.ic_lo)),
                    min(100.,prediction.pct_13+factor*(prediction.ic_hi-prediction.pct_13)))


def calibrate_intervals(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Escolhe o menor fator que cobre pelo menos 90% de cada faixa de 2022."""
    if not records or any(row["ano"]!=2022 for row in records):
        raise ValueError("Calibração aceita somente registros de 2022")
    factors = {}
    for model in ("M1","M2","M3"):
        factors[model] = {}
        for band in range(10):
            rows = [row for row in records if row["modelo"]==model and progress_band(row["pct_apurado"])==band]
            if not rows:
                raise ValueError(f"Faixa de calibração ausente: {model}, {band}")
            scores = []
            for row in rows:
                difference = row["real"]-row["previsto"]
                half = row["ic_hi_bruto"]-row["previsto"] if difference>=0 else row["previsto"]-row["ic_lo_bruto"]
                if half<=0 and abs(difference)>1e-12:
                    raise ValueError("Intervalo estrutural degenerado não admite calibração multiplicativa")
                scores.append(abs(difference)/half if half>0 else 0.)
            rank = math.ceil(0.9*len(scores))
            factor = float(sorted(scores)[rank-1])
            factors[model][str(band)] = {
                "inicio":band*10+1,"fim":min((band+1)*10,99),"n":len(rows),
                "fator":factor,"ordem_quantil":rank,
                "cobertura_bruta":sum(row["ic_lo_bruto"]<=row["real"]<=row["ic_hi_bruto"] for row in rows)/len(rows),
                "cobertura_calibracao":sum(score<=factor+1e-12 for score in scores)/len(scores),
            }
    return {"versao":"choques-uf-nacional-v1","ano_calibracao":2022,"nivel_nominal":0.90,
            "congelado_em":datetime.now(timezone.utc).isoformat(),"fatores":factors,
            "metodo":"Quantil empírico de erro absoluto dividido pela semilargura do lado do erro; faixas fixas de 10 marcos.",
            "limitacao":"Calibração no mesmo ano de desenvolvimento, com snapshots dependentes; não há garantia conformal de cobertura fora da amostra."}


def _initialize_worker(year: int, root: str, jobs: int) -> None:
    """Carrega o universo uma vez por processo trabalhador."""
    global _ORDERED,_INDICATORS,_CUTS,_JOBS
    base = Path(root)
    _ORDERED = ordered_sections(pl.read_parquet(base / "data" / "processed" / f"pareado_{year}.parquet"))
    _INDICATORS = pl.read_parquet(base / "data" / "processed" / f"indicadores_{year}.parquet")
    _CUTS = cut_points(_ORDERED.height)
    _JOBS = jobs


def _predict_task(task: tuple[int,int,str]) -> dict[str, Any]:
    """Calcula um intervalo estrutural sem fator empírico nem verdade das faltantes."""
    year,mark,name = task
    assert _ORDERED is not None
    count = _CUTS[mark-1]
    snapshot = Snapshot(count/_ORDERED.height,_ORDERED["recebido_em"][count-1],
                        _ORDERED.slice(0,count),_ORDERED.slice(count))
    start = perf_counter()
    prediction = MODEL_CLASSES[name](indicadores=_INDICATORS,calibrar_ic=False,n_jobs=_JOBS).prever(snapshot)
    return {"ano":year,"modelo":name,"marco":mark,"pct_apurado":snapshot.pct_apurado,
            "horario_corte":snapshot.horario_corte.isoformat(),"previsto":float(prediction.pct_13),
            "ic_lo_bruto":float(prediction.ic_lo),"ic_hi_bruto":float(prediction.ic_hi),
            "segundos":perf_counter()-start}


def experiment_signature(root: Path) -> str:
    """Identifica código, configuração e entradas para impedir reuso de cache antigo."""
    digest = hashlib.sha256()
    paths = [root / "src" / "apuracao" / name for name in ("models.py","evaluate.py","features.py","simulate.py")]
    paths += [root / "docs" / "CALIBRACAO_K.json"]
    paths += [root / "data" / "processed" / f"{kind}_{year}.parquet"
              for year in (2022,2026) for kind in ("pareado","indicadores")]
    for path in paths:
        digest.update(path.name.encode())
        with path.open("rb") as source:
            digest.update(hashlib.file_digest(source,"sha256").digest())
    return digest.hexdigest()[:20]


def raw_year(year: int, root: Path, signature: str, workers: int, jobs: int) -> list[dict[str, Any]]:
    """Executa tarefas independentes com checkpoints retomáveis e limite de threads."""
    folder = root / "data" / "processed" / "avaliacao_cache" / signature / str(year)
    folder.mkdir(parents=True,exist_ok=True)
    tasks = [(year,mark,name) for mark in range(1,100) for name in MODEL_CLASSES]
    records,pending = [],[]
    for task in tasks:
        path = folder / f"{task[2]}_{task[1]:02}.json"
        if path.exists():
            records.append(read_json(path))
        else:
            pending.append(task)
    print(f"{year}: {len(records)}/396 tarefas em cache; {len(pending)} pendentes",flush=True)
    start = perf_counter()
    os.environ["POLARS_MAX_THREADS"] = str(jobs)
    with ProcessPoolExecutor(max_workers=workers,initializer=_initialize_worker,initargs=(year,str(root),jobs)) as executor:
        futures = {executor.submit(_predict_task,task):task for task in pending}
        for future in as_completed(futures):
            record = future.result()
            write_json(folder / f"{record['modelo']}_{record['marco']:02}.json",record)
            records.append(record)
            progress = {"ano":year,"concluidas":len(records),"total":396,
                        "segundos_fase":perf_counter()-start,"ultima":{"modelo":record["modelo"],"marco":record["marco"]}}
            write_json(root / "data" / "processed" / "avaliacao_progresso.json",progress)
            if len(records)%12==0 or len(records)==396:
                print(progress,flush=True)
    for record in records:
        truth = OFFICIAL_TOTALS[year]
        record["real"] = 100*truth["votos_A"]/truth["votos_validos"]
    return sorted(records,key=lambda record:(record["marco"],record["modelo"]))


def final_rows(records: list[dict[str, Any]], calibration: dict[str, Any]) -> list[dict[str, Any]]:
    """Escala os intervalos sem alterar nenhuma previsão pontual."""
    result = []
    for record in records:
        raw = Previsao(record["previsto"],record["ic_lo_bruto"],record["ic_hi_bruto"])
        prediction = apply_ic_calibration(raw,record["modelo"],record["pct_apurado"],calibration)
        factor = 1. if record["modelo"]=="M0" else calibration["fatores"][record["modelo"]][str(progress_band(record["pct_apurado"]))]["fator"]
        result.append(record | {"ic_lo":prediction.ic_lo,"ic_hi":prediction.ic_hi,
                                "erro_pp":record["previsto"]-record["real"],
                                "cobriu":prediction.ic_lo-1e-12<=record["real"]<=prediction.ic_hi+1e-12,
                                "fator_ic":factor})
    return result


def winner_stability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Localiza a última troca de líder e confere o líder estável com o resultado."""
    ordered = sorted(rows,key=lambda row:row["pct_apurado"])
    leaders = [13 if row["previsto"]>50 else 22 if row["previsto"]<50 else 0 for row in ordered]
    last = leaders[-1]
    last_change = max((index for index,leader in enumerate(leaders) if leader!=last),default=-1)
    truth = 13 if ordered[-1]["real"]>50 else 22 if ordered[-1]["real"]<50 else 0
    return {"lider_em_99":last,"estavel_desde":ordered[last_change+1]["pct_apurado"],
            "marco_estavel":ordered[last_change+1]["marco"],"confere_final":last==truth}


def write_results(records: list[dict[str, Any]], execution: dict[str, Any], root: Path) -> None:
    """Escreve o resumo completo, distinguindo desenvolvimento e teste externo."""
    lines = ["# Resultados da avaliação", "",
             "Ordem em que os boletins chegaram ao TSE. Cortes de 1% a 99% das seções com BU; "
             "empates pela chave da seção. Percentuais de progresso nas tabelas são marcos arredondados.","",
             "**2022 = desenvolvimento/calibração (k e fator do IC escolhidos aqui).**", "",
             "**2026 = teste fora da amostra.** Os fatores dos intervalos foram congelados antes "
             "de iniciar a execução de 2026; não houve reajuste pelo desempenho no teste.","",
             f"Tempo total desta execução: **{execution['tempo_total_s']/60:.2f} minutos** "
             f"({execution['tempo_total_s']:.2f} s); {execution['workers']} processos, "
             f"{execution['n_jobs']} threads LightGBM por processo e 200 reamostragens por intervalo.",""]
    summaries = []
    for year in (2022,2026):
        lines += [f"## {year}","","| Modelo | Erro em 10% (p.p.) | Erro em 30% (p.p.) | Erro em 50% (p.p.) | Cobertura IC | Líder estável desde | Líder em 99% | Confere final? |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
        for name in MODEL_CLASSES:
            rows = [row for row in records if row["ano"]==year and row["modelo"]==name]
            sample = {row["marco"]:row for row in rows}
            coverage = sum(row["cobriu"] for row in rows)/len(rows)
            stability = winner_stability(rows)
            summaries.append({"ano":year,"modelo":name,"cobertura":coverage,**stability})
            label = "sem IC" if name=="M0" else f"{100*coverage:.2f}% ({sum(row['cobriu'] for row in rows)}/{len(rows)})"
            lines.append(f"| {name} | {sample[10]['erro_pp']:+.4f} | {sample[30]['erro_pp']:+.4f} | {sample[50]['erro_pp']:+.4f} | {label} | {stability['marco_estavel']}% | {'empate' if stability['lider_em_99']==0 else 'candidato '+str(stability['lider_em_99'])} | {'sim' if stability['confere_final'] else 'não'} |")
        lines += ["","| Modelo | Largura média do IC (p.p.) | Cobertura estrutural antes do fator |",
                  "| --- | ---: | ---: |"]
        for name in ("M1","M2","M3"):
            rows = [row for row in records if row["ano"]==year and row["modelo"]==name]
            before = sum(row["ic_lo_bruto"]<=row["real"]<=row["ic_hi_bruto"] for row in rows)/len(rows)
            width = float(np.mean([row["ic_hi"]-row["ic_lo"] for row in rows]))
            lines.append(f"| {name} | {width:.4f} | {100*before:.2f}% |")
        lines.append("")
    lines += ["## Interpretação e limites", "",
              "A estabilidade do vencedor é uma constatação retrospectiva da projeção pontual "
              "nos cortes até 99%; não significa que o intervalo já excluía 50% naquele instante.","",
              "A cobertura é a proporção dos 99 cortes cujo intervalo contém o único resultado "
              "nacional final. Os cortes são dependentes; não são 99 eleições independentes. "
              "A calibração por faixas é empírica, inspirada em escores conformais, sem garantia "
              "conformal de 90% no ano seguinte. A cobertura em 2022 é ajustada por construção.","",
              "M0 é uma parcial sem intervalo inferencial: o Parquet mantém os limites degenerados "
              "e o campo cobriu, mas não se atribui cobertura nominal de 90% a esse modelo.","",
              "Fontes de totais: arquivos oficiais independentes do BU registrados em config.py. "
              "Indicadores: edições históricas publicadas até 2021, documentadas em FONTES_MODELOS.md. "
              "Calibração fixa: [CALIBRACAO_IC.json](CALIBRACAO_IC.json).", ""]
    (root / "docs" / "RESULTADOS.md").write_text("\n".join(lines),encoding="utf-8")
    write_json(root / "docs" / "RESULTADOS_RESUMO.json",summaries)


def evaluate(root: Path = ROOT, workers: int = 2, jobs: int = 2) -> None:
    """Executa desenvolvimento, congela a calibração e somente então avalia 2026."""
    started = perf_counter()
    signature = experiment_signature(root)
    records_2022 = raw_year(2022,root,signature,workers,jobs)
    calibration = calibrate_intervals(records_2022)
    calibration["assinatura_experimento"] = signature
    calibration["k"] = read_json(root / "docs" / "CALIBRACAO_K.json")["k_escolhido"]
    calibration_path = root / "docs" / "CALIBRACAO_IC.json"
    write_json(calibration_path,calibration)
    frozen_hash = hashlib.sha256(calibration_path.read_bytes()).hexdigest()
    print(f"Calibração 2022 congelada: SHA-256 {frozen_hash}. Iniciando teste 2026.",flush=True)
    records_2026 = raw_year(2026,root,signature,workers,jobs)
    if hashlib.sha256(calibration_path.read_bytes()).hexdigest()!=frozen_hash:
        raise ValueError("Calibração alterada durante o teste de 2026")
    records = final_rows(records_2022+records_2026,calibration)
    frame = pl.DataFrame(records).with_columns(pl.col("horario_corte").str.to_datetime(time_zone="UTC")).sort("ano","marco","modelo")
    if frame.height!=792 or frame.select("ano","modelo","marco").is_duplicated().any():
        raise ValueError("Grade de avaliação incompleta ou duplicada")
    path = root / "data" / "processed" / "avaliacao.parquet"
    partial = path.with_suffix(".parquet.part")
    frame.write_parquet(partial,compression="zstd")
    partial.replace(path)
    execution = {"tempo_total_s":perf_counter()-started,"workers":workers,"n_jobs":jobs,
                 "assinatura":signature,"calibracao_sha256":frozen_hash,
                 "terminou_em":datetime.now(timezone.utc).isoformat()}
    write_json(root / "docs" / "AVALIACAO_EXECUCAO.json",execution)
    write_results(records,execution,root)
    print(execution,flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers",type=int,choices=(1,2,3,4),default=2)
    parser.add_argument("--n-jobs",type=int,choices=(1,2,3,4),default=2)
    args = parser.parse_args()
    evaluate(workers=args.workers,jobs=args.n_jobs)
