"""Projeções do candidato 13 com informações disponíveis no snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import polars as pl
from lightgbm import LGBMRegressor

from apuracao.features import FEATURES
from apuracao.download import ROOT, read_json, write_json
from apuracao.simulate import REGIONS, Snapshot

BASE = ["pct_A_base", "comparec_base", "bn_base"]
# Esta é a única lista de colunas lidas das seções faltantes.
KNOWN = ["uf", "cod_municipio", "aptos", *BASE]


@dataclass(frozen=True, slots=True)
class Previsao:
    """Guarda o percentual do candidato 13 e os limites do intervalo de 90%."""

    pct_13: float
    ic_lo: float
    ic_hi: float


def observed(frame: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Calcula taxas e pesos apenas dos votos e eleitores já apurados."""
    aptos = frame["aptos"].to_numpy().astype(float)
    comparec = frame["comparecimento"].to_numpy().astype(float)
    valid = frame["votos_validos"].to_numpy().astype(float)
    votes = frame["votos_13"].to_numpy().astype(float)
    rates = np.column_stack([
        np.divide(votes, valid, out=np.zeros_like(valid), where=valid>0),
        np.divide(comparec, aptos, out=np.zeros_like(aptos), where=aptos>0),
        np.divide(comparec-valid, comparec, out=np.zeros_like(valid), where=comparec>0),
    ])
    return rates, np.column_stack([valid, aptos, comparec])


def grouped_swings(frame: pl.DataFrame, residual: np.ndarray, weights: np.ndarray,
                   keys: list[str]) -> dict[tuple[str, ...], tuple[np.ndarray, np.ndarray]]:
    """Resume desvios ponderados e número de seções com denominador válido."""
    arrays = {f"r{j}":residual[:,j]*weights[:,j] for j in range(3)}
    arrays |= {f"w{j}":weights[:,j] for j in range(3)}
    arrays |= {f"n{j}":(weights[:,j]>0).astype(int) for j in range(3)}
    groups = (frame.select(keys).hstack(pl.DataFrame(arrays)).group_by(keys).agg(
        *[pl.col(f"{kind}{j}").sum() for kind in ("r","w","n") for j in range(3)]))
    result = {}
    for row in groups.iter_rows(named=True):
        weight = np.array([row[f"w{j}"] for j in range(3)],dtype=float)
        numerator = np.array([row[f"r{j}"] for j in range(3)],dtype=float)
        result[tuple(row[key] for key in keys)] = (
            np.divide(numerator,weight,out=np.zeros(3),where=weight>0),
            np.array([row[f"n{j}"] for j in range(3)],dtype=float))
    return result


class Modelo:
    """Projeta faltantes usando somente chaves, aptos e taxas do ano base."""

    def __init__(self, *, k: float | None = None, n_bootstrap: int = 200, seed: int = 42,
                 indicadores: pl.DataFrame | None = None, min_train: int = 2000) -> None:
        """Configura parâmetros fixos e, opcionalmente, indicadores históricos."""
        if k is None:
            calibration = ROOT / "docs" / "CALIBRACAO_K.json"
            k = float(read_json(calibration)["k_escolhido"]) if calibration.exists() else 20
        if k<0 or n_bootstrap<0 or min_train<1:
            raise ValueError("Parâmetros negativos ou limiar de treino inválido")
        self.k,self.n_bootstrap,self.seed = k,n_bootstrap,seed
        self.indicadores,self.min_train = indicadores,min_train

    def _hierarchy(self, obs: pl.DataFrame, residual: np.ndarray, weights: np.ndarray,
                   frames: list[pl.DataFrame]) -> tuple[list[np.ndarray], list[np.ndarray]]:
        """Encolhe município para UF e UF para país para as três taxas."""
        den = weights.sum(axis=0)
        national = np.divide((residual*weights).sum(axis=0),den,out=np.zeros(3),where=den>0)
        ufs = grouped_swings(obs,residual,weights,["uf"])
        municipalities = grouped_swings(obs,residual,weights,["uf","cod_municipio"])
        cache = {}
        all_keys = set().union(*(set(frame.select("uf","cod_municipio").iter_rows()) for frame in frames))
        for uf,municipality in all_keys:
            uf_mean,uf_n = ufs.get((uf,),(national,np.zeros(3)))
            uf_swing = np.divide(uf_n*uf_mean+self.k*national,uf_n+self.k,
                                 out=national.copy(),where=(uf_n+self.k)>0)
            mun_mean,mun_n = municipalities.get((uf,municipality),(uf_swing,np.zeros(3)))
            mun_swing = np.divide(mun_n*mun_mean+self.k*uf_swing,mun_n+self.k,
                                  out=uf_swing.copy(),where=(mun_n+self.k)>0)
            cache[(uf,municipality)] = (mun_swing,[*mun_swing,*uf_swing,mun_n[0],uf_n[0]])
        predicted,features = [],[]
        for frame in frames:
            values = [cache[key] for key in frame.select("uf","cod_municipio").iter_rows()]
            predictions = [value[0] for value in values]
            local_features = [value[1] for value in values]
            predicted.append(np.array(predictions,dtype=float).reshape(-1,3))
            features.append(np.array(local_features,dtype=float).reshape(-1,8))
        return predicted,features

    def _swings(self, obs: pl.DataFrame, missing: pl.DataFrame, residual: np.ndarray,
                weights: np.ndarray, cutoff: date) -> tuple[np.ndarray,np.ndarray]:
        """Fornece os swings previstos nas apuradas e faltantes."""
        raise NotImplementedError

    def prever(self, snapshot: Snapshot) -> Previsao:
        """Combina os votos apurados com a projeção e o bootstrap das faltantes."""
        obs = snapshot.apuradas.select(*KNOWN,"votos_13","votos_validos","comparecimento")
        # Descartar fisicamente todas as colunas de resultados das faltantes.
        missing = snapshot.faltantes.select(KNOWN)
        known_a,known_valid = float(obs["votos_13"].sum()),float(obs["votos_validos"].sum())
        if known_valid<=0:
            raise ValueError("Snapshot sem votos válidos apurados")
        if not missing.height:
            pct = 100*known_a/known_valid
            return Previsao(pct,pct,pct)
        rates,weights = observed(obs)
        base_observed = obs.select(BASE).to_numpy().astype(float)
        base_missing = missing.select(BASE).to_numpy().astype(float)
        if not np.isfinite(base_observed).all() or not np.isfinite(base_missing).all():
            raise ValueError("Taxas históricas ausentes; regenerar o pareamento")
        residual = rates-base_observed
        train_swing,future_swing = self._swings(obs,missing,residual,weights,snapshot.horario_corte.date())
        future_rates = np.clip(base_missing+future_swing,0,1)
        aptos = missing["aptos"].to_numpy().astype(float)

        def project(predicted: np.ndarray) -> float:
            """Agrega votos válidos previstos sem consultar votos das faltantes."""
            valid = aptos*predicted[:,1]*(1-predicted[:,2])
            return 100*(known_a+(valid*predicted[:,0]).sum())/(known_valid+valid.sum())

        pct = project(future_rates)
        if self.n_bootstrap==0:
            return Previsao(pct,pct,pct)
        errors = rates-np.clip(base_observed+train_swing,0,1)
        blocks = grouped_swings(obs,errors,weights,["uf","cod_municipio"])
        block_errors = np.array([value[0] for _,value in sorted(blocks.items())])
        block_errors -= block_errors.mean(axis=0)
        # Uma perturbação conjunta por município faltante, preservando o bloco.
        future_keys = list(missing.select("uf","cod_municipio").iter_rows())
        key_index = {key:i for i,key in enumerate(sorted(set(future_keys)))}
        codes = np.array([key_index[key] for key in future_keys])
        rng = np.random.default_rng(self.seed)
        draws = np.empty(self.n_bootstrap)
        for draw in range(self.n_bootstrap):
            selected = rng.integers(0,len(block_errors),size=len(key_index))
            adjusted = np.clip(future_rates+block_errors[selected][codes],0,1)
            draws[draw] = project(adjusted)
        lo,hi = np.quantile(draws,[0.05,0.95])
        return Previsao(pct,float(lo),float(hi))


class M0(Modelo):
    """Retorna a parcial ingênua, sem intervalo de confiança."""

    def prever(self, snapshot: Snapshot) -> Previsao:
        """Calcula o percentual do candidato 13 entre os votos já apurados."""
        valid = snapshot.apuradas["votos_validos"].sum()
        if valid<=0:
            raise ValueError("Snapshot sem votos válidos apurados")
        pct = 100*snapshot.apuradas["votos_13"].sum()/valid
        return Previsao(pct,pct,pct)


class M1(Modelo):
    """Aplica o swing nacional ponderado às três taxas históricas."""

    def _swings(self, obs: pl.DataFrame, missing: pl.DataFrame, residual: np.ndarray,
                weights: np.ndarray, cutoff: date) -> tuple[np.ndarray,np.ndarray]:
        """Estima o desvio nacional pelos denominadores observados de cada taxa."""
        total = weights.sum(axis=0)
        swing = np.divide((residual*weights).sum(axis=0),total,out=np.zeros(3),where=total>0)
        return np.tile(swing,(obs.height,1)),np.tile(swing,(missing.height,1))


class M2(Modelo):
    """Aplica shrinkage de município para UF e país, com k configurável."""

    def _swings(self, obs: pl.DataFrame, missing: pl.DataFrame, residual: np.ndarray,
                weights: np.ndarray, cutoff: date) -> tuple[np.ndarray,np.ndarray]:
        """Retorna os desvios hierárquicos das três taxas."""
        swings,_ = self._hierarchy(obs,residual,weights,[obs,missing])
        return swings[0],swings[1]


def calibration_snapshots(year: int, root: Path = ROOT) -> list[Snapshot]:
    """Seleciona apenas os quatro cortes autorizados para aferição rápida."""
    from apuracao.simulate import ordered_sections, snapshots_from_ordered

    ordered = ordered_sections(pl.read_parquet(root / "data" / "processed" / f"pareado_{year}.parquet"))
    return [snapshot for index,snapshot in enumerate(snapshots_from_ordered(ordered),start=1) if index in (1,10,30,50)]


def calibrate_k(root: Path = ROOT) -> dict[str, Any]:
    """Escolhe k em poucos cortes de 2022 e congela a escolha para 2026."""
    from apuracao.config import OFFICIAL_TOTALS

    cuts = calibration_snapshots(2022,root)
    real = 100*OFFICIAL_TOTALS[2022]["votos_A"]/OFFICIAL_TOTALS[2022]["votos_validos"]
    scores = []
    for k in (5,20,100):
        errors = [abs(M2(k=k,n_bootstrap=0).prever(snapshot).pct_13-real) for snapshot in cuts]
        scores.append({"k":k,"mae_pp":float(np.mean(errors)),"erros_pp":errors})
    chosen = min(scores,key=lambda row:(row["mae_pp"],abs(row["k"]-20)))
    report = {"ano_calibracao":2022,"marcos":[1,10,30,50],"criterio":"MAE da projeção pontual M2",
              "k_escolhido":chosen["k"],"candidatos":scores,
              "limitacao":"Cortes usados para escolher k são calibração, não teste independente."}
    write_json(root / "docs" / "CALIBRACAO_K.json",report)
    print(report,flush=True)
    return report


def benchmark(root: Path = ROOT, years: tuple[int, ...] = (2022,2026)) -> None:
    """Mede os quatro modelos em poucos cortes, sem executar a avaliação completa."""
    from apuracao.config import OFFICIAL_TOTALS

    records = []
    for year in years:
        indicators = pl.read_parquet(root / "data" / "processed" / f"indicadores_{year}.parquet")
        real = 100*OFFICIAL_TOTALS[year]["votos_A"]/OFFICIAL_TOTALS[year]["votos_validos"]
        for mark,snapshot in zip((1,10,30,50),calibration_snapshots(year,root)):
            for cls in (M0,M1,M2,M3):
                model = cls(indicadores=indicators)
                start = perf_counter()
                prediction = model.prever(snapshot)
                seconds = perf_counter()-start
                record = {"ano":year,"marco":mark,"modelo":cls.__name__,"pct_apurado":snapshot.pct_apurado,
                          "previsto":prediction.pct_13,"ic_lo":prediction.ic_lo,"ic_hi":prediction.ic_hi,
                          "real":real,"erro_pp":prediction.pct_13-real,"segundos":seconds,
                          "bootstrap":0 if cls is M0 else model.n_bootstrap,"k":model.k}
                records.append(record)
                print(record,flush=True)
    path = root / "docs" / "BENCHMARK_MODELOS.json"
    previous = read_json(path) if path.exists() else []
    records += [record for record in previous if record["ano"] not in years]
    write_json(path,sorted(records,key=lambda record:(record["ano"],record["marco"],record["modelo"])))
    document_models(root)


class M3(Modelo):
    """Prevê swing com LightGBM e usa M2 abaixo do limiar mínimo de treino."""

    def _features(self, frame: pl.DataFrame, local: np.ndarray, cutoff: date) -> np.ndarray:
        """Monta somente características permitidas e indicadores já publicados."""
        indicators = self.indicadores
        if indicators is None:
            path = ROOT / "data" / "processed" / f"indicadores_{cutoff.year}.parquet"
            if not path.exists():
                raise ValueError("M3 exige indicadores históricos; executar apuracao.features")
            indicators = pl.read_parquet(path)
        if indicators["ibge_publicado_em"].null_count() or indicators["ibge_publicado_em"].max()>cutoff:
            raise ValueError("Indicador IBGE sem data ou publicado depois do snapshot")
        joined = frame.select("uf","cod_municipio").join(indicators,on=["uf","cod_municipio"],how="left",validate="m:1",maintain_order="left")
        ibge = joined.select(FEATURES).to_numpy().astype(float)
        ibge = np.log1p(ibge)
        uf_codes = {uf:i for i,uf in enumerate(sorted(REGIONS))}
        region_codes = {region:i for i,region in enumerate(sorted(set(REGIONS.values())))}
        uf = np.array([uf_codes[value] for value in frame["uf"]])
        region = np.array([region_codes[REGIONS[value]] for value in frame["uf"]])
        return np.column_stack([frame.select(BASE).to_numpy(),region,uf,local,ibge])

    def _swings(self, obs: pl.DataFrame, missing: pl.DataFrame, residual: np.ndarray,
                weights: np.ndarray, cutoff: date) -> tuple[np.ndarray,np.ndarray]:
        """Treina apenas nas apuradas e reutiliza o ajuste no bootstrap."""
        swings,local = self._hierarchy(obs,residual,weights,[obs,missing])
        if obs.height<self.min_train:
            return swings[0],swings[1]
        train = self._features(obs,local[0],cutoff)
        future = self._features(missing,local[1],cutoff)
        for j in range(3):
            valid = weights[:,j]>0
            model = LGBMRegressor(n_estimators=200,learning_rate=0.05,num_leaves=15,
                              max_depth=6,min_child_samples=40,n_jobs=4,random_state=self.seed,
                              deterministic=True,force_col_wise=True,verbosity=-1)
            model.fit(train[valid],residual[valid,j],sample_weight=weights[valid,j],categorical_feature=[3,4])
            swings[0][:,j] = model.predict(train)
            swings[1][:,j] = model.predict(future)
        return swings[0],swings[1]


def document_models(root: Path = ROOT) -> None:
    """Registra previsões, cobertura preliminar dos intervalos e tempos medidos."""
    records = read_json(root / "docs" / "BENCHMARK_MODELOS.json")
    lines = ["## Aferição rápida dos modelos (Prompt 5)","",
             "Percentuais do candidato 13 nos votos válidos, na ordem em que os boletins chegaram ao TSE. "
             "Somente cortes de 1%, 10%, 30% e 50%; não é a avaliação completa.","",
             "| Ano | Corte | Modelo | Previsto (%) | Erro (p.p.) | Intervalo nominal 90% | Inclui o final? | Tempo (s) |",
             "| --- | ---: | --- | ---: | ---: | --- | --- | ---: |"]
    for row in records:
        if row["ano"]==2022 and row["marco"] in (10,30):
            interval = "sem IC" if row["modelo"]=="M0" else f"[{row['ic_lo']:.4f}; {row['ic_hi']:.4f}]"
            covers = "—" if row["modelo"]=="M0" else ("sim" if row["ic_lo"]<=row["real"]<=row["ic_hi"] else "não")
            lines.append(f"| {row['ano']} | {row['marco']}% | {row['modelo']} | {row['previsto']:.4f} | {row['erro_pp']:+.4f} | {interval} | {covers} | {row['segundos']:.4f} |")
    lines += ["","| Ano | Corte | M0 (s) | M1 (s) | M2 (s) | M3 (s) |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for year in (2022,2026):
        for mark in (1,10,30,50):
            group = {row["modelo"]:row for row in records if row["ano"]==year and row["marco"]==mark}
            if len(group)==4:
                lines.append(f"| {year} | {mark}% | " + " | ".join(f"{group[model]['segundos']:.4f}" for model in ("M0","M1","M2","M3")) + " |")
    lines += ["", "Tempos pontuais desta máquina, não um teste de latência isolado. "
              "Excluem importação e leitura/ordenação dos Parquets; incluem preparação de características, "
              "treino e 200 reamostragens para M1–M3. M0 não faz bootstrap.","",
              "A meta pontual <1 p.p. a 30% foi atingida nesta aferição de 2022 por M1–M3. "
              "Os mesmos cortes de 2022 participaram da seleção de k; logo não são teste independente "
              "da calibração. Os intervalos de M1, M2 e M3 em 30% de 2022 não contiveram o final. "
              "A cobertura nominal de 90% não está demonstrada; avaliar a cobertura no Prompt 6, "
              "sem ajustar intervalos para encaixar o resultado de 2026.",""]
    method = root / "docs" / "METODO.md"
    existing = method.read_text(encoding="utf-8")
    start,end = "<!-- inicio:modelos-benchmark -->","<!-- fim:modelos-benchmark -->"
    block = start+"\n"+"\n".join(lines)+"\n"+end
    if start in existing and end in existing:
        before,rest = existing.split(start,1)
        _,after = rest.split(end,1)
        content = before+block+after
    else:
        content = existing.rstrip()+"\n\n"+block+"\n"
    method.write_text(content,encoding="utf-8")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibrar-k",action="store_true")
    parser.add_argument("--ano",type=int,choices=(2022,2026),nargs="+",default=[2022,2026])
    args = parser.parse_args()
    if args.calibrar_k:
        calibrate_k()
    else:
        benchmark(years=tuple(args.ano))
