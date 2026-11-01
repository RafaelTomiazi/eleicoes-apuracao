"""Diagnóstico retrospectivo por componentes, sem alterar as previsões avaliadas."""

from __future__ import annotations

import hashlib
import itertools
import math
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from apuracao.download import ROOT, read_json, write_json
from apuracao.models import BASE, KNOWN, M3, observed
from apuracao.simulate import snapshots

COMPONENTS = ("comparecimento", "brancos_nulos", "swing", "exterior")


def fingerprint(path: Path) -> str:
    """Calcula a identidade do arquivo que deve permanecer intacto."""
    with path.open("rb") as source:
        return hashlib.file_digest(source,"sha256").hexdigest()


def project_rates(rates: np.ndarray, aptos: np.ndarray, known_a: float, known_valid: float) -> float:
    """Agrega votos conhecidos e taxas propostas para as faltantes."""
    valid = aptos*rates[:,1]*(1-rates[:,2])
    return float(100*(known_a+(valid*rates[:,0]).sum())/(known_valid+valid.sum()))


def oracle_decomposition(predicted: np.ndarray, truth: np.ndarray, aptos: np.ndarray,
                         exterior: np.ndarray, known_a: float, known_valid: float,
                         final_pct: float) -> dict[str, Any]:
    """Atribui o erro por Shapley, separando taxas domésticas e todo o exterior."""
    errors = {}
    for mask in range(16):
        rates = predicted.copy()
        for index,column in ((0,1),(1,2),(2,0)):
            if mask & (1<<index):
                rates[~exterior,column] = truth[~exterior,column]
        if mask & 8:
            rates[exterior] = truth[exterior]
        errors[mask] = project_rates(rates,aptos,known_a,known_valid)-final_pct
    contributions = dict.fromkeys(COMPONENTS,0.)
    for permutation in itertools.permutations(range(4)):
        mask = 0
        for component in permutation:
            updated = mask | (1<<component)
            contributions[COMPONENTS[component]] += (errors[mask]-errors[updated])/math.factorial(4)
            mask = updated
    if abs(errors[15])>1e-9 or abs(sum(contributions.values())-errors[0])>1e-9:
        raise ValueError("Decomposição não reconcilia o erro total com o resultado final")
    return {"erro_pp":errors[0],"erro_todas_taxas_reais_pp":errors[15],
            "contribuicoes_shapley_pp":contributions,
            "erro_apos_corrigir_so_componente_pp":{name:errors[1<<i] for i,name in enumerate(COMPONENTS)}}


def diagnose_year(year: int, root: Path = ROOT) -> dict[str, Any]:
    """Reconstrói somente o corte de 30% e revela as faltantes depois do ajuste."""
    snapshot = next(snapshot for index,snapshot in enumerate(snapshots(year),1) if index==30)
    obs = snapshot.apuradas.select(*KNOWN,"votos_13","votos_validos","comparecimento")
    missing = snapshot.faltantes.select(KNOWN)
    rates,weights = observed(obs)
    residual = rates-obs.select(BASE).to_numpy()
    model = M3(n_bootstrap=0,calibrar_ic=False,n_jobs=1)
    _,future_swing = model._swings(obs,missing,residual,weights,snapshot.horario_corte.date())
    predicted = np.clip(missing.select(BASE).to_numpy()+future_swing,0,1)
    # Somente após congelar as predições: leitura oracular para diagnóstico.
    truth,_ = observed(snapshot.faltantes)
    aptos = missing["aptos"].to_numpy().astype(float)
    exterior = missing["uf"].to_numpy()=="ZZ"
    known_a,known_valid = float(obs["votos_13"].sum()),float(obs["votos_validos"].sum())
    evaluation = pl.read_parquet(root / "data" / "processed" / "avaliacao.parquet")
    reference = evaluation.filter((pl.col("ano")==year)&(pl.col("modelo")=="M3")&(pl.col("marco")==30)).row(0,named=True)
    forecast = project_rates(predicted,aptos,known_a,known_valid)
    if abs(forecast-reference["previsto"])>1e-8:
        raise ValueError("Diagnóstico não reproduziu a previsão congelada do M3")
    result = oracle_decomposition(predicted,truth,aptos,exterior,known_a,known_valid,reference["real"])
    predicted_turnout = aptos*predicted[:,1]
    predicted_valid = predicted_turnout*(1-predicted[:,2])
    actual_turnout = float(snapshot.faltantes["comparecimento"].sum())
    actual_valid = float(snapshot.faltantes["votos_validos"].sum())
    actual_a = float(snapshot.faltantes["votos_13"].sum())
    result |= {"ano":year,"marco":30,"pct_apurado":snapshot.pct_apurado,"previsto":forecast,"real":reference["real"],
               "secoes_faltantes":missing.height,"secoes_exterior_faltantes":int(exterior.sum()),
               "taxas_agregadas_faltantes":{
                   "comparecimento_previsto":float(predicted_turnout.sum()/aptos.sum()),
                   "comparecimento_real":actual_turnout/float(aptos.sum()),
                   "bn_previsto":float(1-predicted_valid.sum()/predicted_turnout.sum()),
                   "bn_real":1-actual_valid/actual_turnout,
                   "pct_13_previsto":float((predicted_valid*predicted[:,0]).sum()/predicted_valid.sum()),
                   "pct_13_real":actual_a/actual_valid}}
    print(result,flush=True)
    return result


def diagnose_all(root: Path = ROOT) -> dict[str, Any]:
    """Salva os diagnósticos e comprova que avaliação e calibrações não mudaram."""
    protected = [root / "data" / "processed" / "avaliacao.parquet",
                 root / "docs" / "CALIBRACAO_IC.json",root / "docs" / "CALIBRACAO_K.json"]
    before = {str(path.relative_to(root)):fingerprint(path) for path in protected}
    records = [diagnose_year(year,root) for year in (2022,2026)]
    after = {str(path.relative_to(root)):fingerprint(path) for path in protected}
    if before!=after:
        raise ValueError("O diagnóstico alterou um artefato protegido")
    evaluation = pl.read_parquet(protected[0])
    means = evaluation.filter(pl.col("modelo").is_in(["M2","M3"])).group_by("ano","modelo").agg(
        pl.col("erro_pp").mean().alias("erro_medio_pp"),pl.col("erro_pp").median().alias("mediana_pp"),
        (pl.col("erro_pp")>0).mean().alias("fracao_cortes_erro_positivo")).sort("ano","modelo")
    report = {"metodo":"Shapley exato de quatro substituições oraculares; só diagnóstico, sem ajuste.",
              "componentes_domesticos":list(COMPONENTS[:3]),"exterior":"Todas as taxas de ZZ corrigidas em bloco, sem dupla contagem.",
              "media_nos_99_cortes":means.to_dicts(),"cortes_30":records,"arquivos_protegidos_sha256":before}
    write_json(root / "docs" / "DIAGNOSTICO_VIES.json",report)
    write_diagnosis_notes(root)
    return report


def diagnostic_table(root: Path = ROOT) -> pl.DataFrame:
    """Retorna a tabela curta de contribuições para exibição no notebook."""
    path = root / "docs" / "DIAGNOSTICO_VIES.json"
    report = read_json(path) if path.exists() else diagnose_all(root)
    return pl.DataFrame([{"ano":row["ano"],"componente":name,"contribuicao_pp":value}
                         for row in report["cortes_30"] for name,value in row["contribuicoes_shapley_pp"].items()])


def write_diagnosis_notes(root: Path = ROOT) -> None:
    """Acrescenta lições e decomposição ao relatório sem reestimar os modelos."""
    report = read_json(root / "docs" / "DIAGNOSTICO_VIES.json")
    calibration = read_json(root / "docs" / "CALIBRACAO_IC.json")
    data = pl.read_parquet(root / "data" / "processed" / "avaliacao.parquet")
    dispersion = {}
    for year in (2022,2026):
        snapshot = next(s for i,s in enumerate(snapshots(year),1) if i==30)
        obs = snapshot.apuradas.filter(pl.col("votos_validos")>0)
        uf = obs.group_by("uf").agg(
            ((pl.col("votos_13")-pl.col("pct_A_base")*pl.col("votos_validos")).sum()/pl.col("votos_validos").sum()).alias("swing"))
        dispersion[str(year)] = float(uf["swing"].std(ddof=1)*100)
    report["dispersao_swing_observado_uf_em_30_pp"] = dispersion
    write_json(root / "docs" / "DIAGNOSTICO_VIES.json",report)
    lines = ["## O que a falha de cobertura ensinou", "",
             "A calibração contraiu a faixa estrutural de 2022. O valor próximo de 0,22 "
             "não representa todos os modelos: os fatores efetivamente salvos são:","",
             "| Modelo | Menor fator | Maior fator | Largura média após/antes, em 2022 |",
             "| --- | ---: | ---: | ---: |"]
    for model in ("M1","M2","M3"):
        factors = [row["fator"] for row in calibration["fatores"][model].values()]
        part = data.filter((pl.col("ano")==2022)&(pl.col("modelo")==model))
        ratio = (part["ic_hi"]-part["ic_lo"]).mean()/(part["ic_hi_bruto"]-part["ic_lo_bruto"]).mean()
        lines.append(f"| {model} | {min(factors):.4f} | {max(factors):.4f} | {ratio:.4f} |")
    raw_width = {}
    for year in (2022,2026):
        part = data.filter((pl.col("ano")==year)&(pl.col("modelo")=="M3"))
        raw_width[year] = (part["ic_hi_bruto"]-part["ic_lo_bruto"]).mean()
    lines += ["",f"No corte de 30%, o desvio-padrão dos swings médios observados por UF "
              f"foi {dispersion['2022']:.4f} p.p. em 2022 e {dispersion['2026']:.4f} p.p. em 2026 "
              "(UFs com válidos já recebidos; dispersão não ponderada entre médias estaduais ponderadas por válidos). "
              f"A largura bruta média do M3 caiu de {raw_width[2022]:.4f} para {raw_width[2026]:.4f} p.p. "
              "A faixa já nasceu mais estreita em 2026 e recebeu a mesma contração de escala. "
              "O erro pontual não diminuiu na mesma proporção.","",
              "Uma eleição de calibração é **uma realização do processo eleitoral**: "
              "os 99 cortes são a mesma noite vista repetidamente e são autocorrelacionados. "
              "Não equivalem a 99 eleições independentes. Isso não permite estimar literalmente "
              "um tamanho amostral efetivo igual a 1, mas há apenas uma eleição de calibração "
              "para julgar a transferência entre eleições.","",
              "**Decisão de apresentação feita APÓS ver 2026:** os gráficos usam a FAIXA "
              "ESTRUTURAL BRUTA, rotulada **faixa conservadora, sem cobertura nominal validada**. "
              "Ela cobriu 100% dos cortes dos dois anos observados. Essa escolha posterior "
              "não é uma validação fora da amostra da escolha de faixa, não retoca o teste e "
              "não demonstra probabilidade de cobertura de 90% em outra eleição. "
              "A avaliação, os fatores e os limites calibrados originais permanecem intactos.","",
              "## Diagnóstico de viés do M3 em 30%", "",
              "Os dados futuros abaixo são usados **apenas para diagnóstico retrospectivo**. "
              "Primeiro reproduz-se a previsão congelada; depois substituem-se, por valores reais, "
              "as taxas das faltantes. Os três componentes de taxas são domésticos; o exterior "
              "é corrigido como quarto bloco, evitando dupla contagem. O Shapley exato das "
              "24 ordens de substituição reparte as interações da razão nacional e soma ao erro total. "
              "Sinal positivo contribui para superestimar o candidato 13; negativo compensa o erro.","",
              "| Componente | 2022 (p.p.) | 2026 (p.p.) |", "| --- | ---: | ---: |"]
    by_year = {row["ano"]:row for row in report["cortes_30"]}
    labels = {"comparecimento":"Comparecimento", "brancos_nulos":"Brancos/nulos", "swing":"Swing / participação prevista", "exterior":"Exterior (ZZ)"}
    for component in COMPONENTS:
        lines.append(f"| {labels[component]} | {by_year[2022]['contribuicoes_shapley_pp'][component]:+.6f} | {by_year[2026]['contribuicoes_shapley_pp'][component]:+.6f} |")
    lines += [f"| **Erro total** | **{by_year[2022]['erro_pp']:+.6f}** | **{by_year[2026]['erro_pp']:+.6f}** |","",
              "A participação prevista (base + swing) é a contribuição dominante nos dois anos. "
              "Em 2026, o comparecimento compensa parte da superestimação; por isso a contribuição "
              "do swing é maior que o erro líquido. Brancos/nulos e ZZ têm efeitos pequenos. "
              "Isso identifica o componente da projeção que carrega o erro, mas não demonstra "
              "a causa do viés no LightGBM. Não se ajustou o swing, k, as árvores nem os intervalos.","",
              "| Ano | Modelo | Erro médio nos 99 cortes (p.p.) | Cortes com erro positivo |",
              "| --- | --- | ---: | ---: |"]
    for row in report["media_nos_99_cortes"]:
        lines.append(f"| {row['ano']} | {row['modelo']} | {row['erro_medio_pp']:+.4f} | {100*row['fracao_cortes_erro_positivo']:.2f}% |")
    lines += ["","O padrão é compatível com viés de superestimação nestes dados. "
              "A faixa +0,1 a +0,2 p.p. descreve o erro médio do M3; M2 em 2022 fica próximo "
              "de +0,3 p.p. Duas eleições não estabelecem uma magnitude universal. "
              "Detalhes e taxas agregadas das faltantes estão em [DIAGNOSTICO_VIES.json](DIAGNOSTICO_VIES.json).",""]
    path = root / "docs" / "RESULTADOS.md"
    existing = path.read_text(encoding="utf-8")
    start,end = "<!-- inicio:licoes-vies -->","<!-- fim:licoes-vies -->"
    block = start+"\n"+"\n".join(lines)+"\n"+end
    if start in existing and end in existing:
        before,rest = existing.split(start,1)
        _,after = rest.split(end,1)
        content = before+block+after
    else:
        content = existing.rstrip()+"\n\n"+block+"\n"
    path.write_text(content,encoding="utf-8")


if __name__ == "__main__":
    diagnose_all()
