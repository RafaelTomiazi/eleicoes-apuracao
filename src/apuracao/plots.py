"""Figuras de apresentação com faixa bruta e seleção posterior explicitadas."""

from __future__ import annotations

import hashlib
import io
import math
import zipfile
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Patch
import numpy as np
import polars as pl

from apuracao.download import ROOT, download, read_json, write_json
from apuracao.evaluate import winner_stability

BLUE = "#356B91"
GRAY = "#626973"


def display_pct(value: float, digits: int = 2) -> str:
    """Formata um percentual com vírgula decimal."""
    return f"{value:.{digits}f}".replace(".",",")


def wrong_leader_spans(partial: pl.DataFrame) -> list[tuple[float,float]]:
    """Identifica intervalos de cortes em que o líder da parcial difere do final."""
    x = partial["pct_apurado"].to_numpy()*100
    values = partial["previsto"].to_numpy()
    final = partial["real"][0]
    wrong = ((values<50)&(final>50))|((values>50)&(final<50))
    spans = []
    start = None
    for i,bad in enumerate(wrong):
        if bad and start is None:
            start = i
        if start is not None and (not bad or i==len(wrong)-1):
            end = i if not bad else i+1
            spans.append((0. if start==0 else float(x[start]),float(x[end]) if end<len(x) else 100.))
            start = None
    return spans


def principal(year: int, root: Path = ROOT) -> Path:
    """Cria a figura principal de 1080×1350 sem mudar nenhum intervalo avaliado."""
    data = pl.read_parquet(root / "data" / "processed" / "avaliacao.parquet").filter(pl.col("ano")==year)
    naive = data.filter(pl.col("modelo")=="M0").sort("marco")
    model = data.filter(pl.col("modelo")=="M3").sort("marco")
    stability_model = winner_stability(model.to_dicts())
    stability_naive = winner_stability(naive.to_dicts())
    if not stability_model["confere_final"] or not stability_naive["confere_final"]:
        raise ValueError("Anotação de vencedor correto não é sustentada pelo resultado")
    x = model["pct_apurado"].to_numpy()*100
    final = model["real"][0]
    with plt.rc_context({"font.family":"DejaVu Sans","font.size":11,"axes.spines.top":False,"axes.spines.right":False}):
        fig = plt.figure(figsize=(7.2,9),dpi=150,facecolor="#FAFBFD")
        fig.text(0.10,0.952,f"{year}  /  "+("TESTE FORA DA AMOSTRA" if year==2026 else "DESENVOLVIMENTO / CALIBRAÇÃO"),fontsize=10.2,color=GRAY,weight="bold")
        fig.text(0.10,0.91,"O modelo apontou o vencedor",fontsize=20,weight="bold",color="#243547")
        fig.text(0.10,0.871,f"desde {stability_model['marco_estavel']}% das seções recebidas",fontsize=20,weight="bold",color="#243547")
        fig.text(0.10,0.83,"Na ordem em que os boletins chegaram ao TSE",fontsize=11,color=GRAY)
        fig.text(0.10,0.773,f"Modelo: vencedor certo desde {stability_model['marco_estavel']}%",fontsize=12,weight="bold",color=BLUE)
        fig.text(0.10,0.745,f"Parcial: desde {stability_naive['marco_estavel']}%",fontsize=12,color=GRAY)
        ax = fig.add_axes([0.11,0.315,0.85,0.365],facecolor="white")
        for start,end in wrong_leader_spans(naive):
            ax.axvspan(start,end,color="#747B83",alpha=0.12,zorder=0)
        ax.fill_between(x,model["ic_lo_bruto"].to_numpy(),model["ic_hi_bruto"].to_numpy(),color=BLUE,alpha=0.17,zorder=1)
        line0, = ax.plot(x,naive["previsto"].to_numpy(),color=GRAY,lw=1.8,label="M0 · parcial",zorder=3)
        line3, = ax.plot(x,model["previsto"].to_numpy(),color=BLUE,lw=2.1,label="M3 · projeção",zorder=4)
        final_line = ax.axhline(final,color="#36424D",ls="--",lw=1.2,label=f"Final · {display_pct(final)}%",zorder=2)
        ax.axhline(50,color="#A2A9B0",ls=":",lw=1)
        ax.set(xlim=(0,100),xlabel="Seções com BU recebidas (%)",ylabel="Candidato 13 nos válidos (%)")
        ax.set_xticks([0,20,40,60,80,100])
        ax.tick_params(labelsize=10)
        ax.grid(axis="y",alpha=0.18)
        ax.legend(handles=[line0,line3,final_line,Patch(facecolor=BLUE,alpha=.17,label="Faixa estrutural bruta")],
                  loc="upper left",bbox_to_anchor=(-0.015,-.14),ncol=2,fontsize=9.4,frameon=False,
                  columnspacing=1.4,handlelength=2)
        fig.text(0.10,0.183,"Sombra cinza: a parcial indicava outro líder.",fontsize=9.5,color=GRAY)
        fig.text(0.10,0.147,"Faixa conservadora,",fontsize=11.3,weight="bold",color="#384A5C")
        fig.text(0.10,0.123,"sem cobertura nominal validada.",fontsize=11.3,weight="bold",color="#384A5C")
        fig.text(0.10,0.086,"Escolha de exibição feita APÓS ver 2026.",fontsize=10.3,weight="bold",color=GRAY)
        fig.text(0.10,0.050,"Estabilidade retrospectiva nos cortes de 1% a 99%.",fontsize=9.1,color=GRAY)
        fig.text(0.10,0.029,"Não implica certeza estatística. Fonte: TSE.",fontsize=9.1,color=GRAY)
        path = root / "reports" / "figures" / f"projecao_{year}.png"
        path.parent.mkdir(parents=True,exist_ok=True)
        fig.savefig(path,dpi=150,facecolor=fig.get_facecolor())
        plt.close(fig)
    return path


def errors(root: Path = ROOT) -> Path:
    """Compara os erros absolutos dos quatro modelos nos dois anos."""
    data = pl.read_parquet(root / "data" / "processed" / "avaliacao.parquet")
    colors = {"M0":"#939BA3","M1":"#687A89","M2":"#5C91AE","M3":"#263F58"}
    with plt.rc_context({"font.family":"DejaVu Sans","font.size":11}):
        fig,axes = plt.subplots(1,2,figsize=(12,5.4),sharey=True)
        fig.subplots_adjust(left=.07,right=.98,top=.81,bottom=.23,wspace=.12)
        for ax,year in zip(axes,(2022,2026)):
            for name in ("M0","M1","M2","M3"):
                part = data.filter((pl.col("ano")==year)&(pl.col("modelo")==name)).sort("marco")
                ax.plot(part["pct_apurado"].to_numpy()*100,np.abs(part["erro_pp"].to_numpy()),
                        label=name,color=colors[name],lw=2.3 if name=="M3" else 1.6,
                        ls={"M0":"-","M1":"--","M2":"-.","M3":"-"}[name])
            ax.set(title=f"{year} · "+("desenvolvimento/calibração" if year==2022 else "teste fora da amostra"),
                   xlabel="Seções com BU recebidas (%)",xlim=(0,100),ylim=(0,None))
            ax.spines[["top","right"]].set_visible(False)
            ax.grid(alpha=.2)
        axes[0].set_ylabel("Erro absoluto (p.p.)")
        fig.suptitle("Erro pontual na ordem em que os boletins chegaram ao TSE",fontsize=15,weight="bold",y=.97)
        fig.legend(*axes[0].get_legend_handles_labels(),ncol=4,loc="lower center",bbox_to_anchor=(.5,.075),frameon=False)
        fig.text(.5,.035,"Cortes de 1% a 99%. M0: parcial; M1: uniforme; M2: hierárquico; M3: LightGBM. Fonte: TSE.",ha="center",fontsize=9,color=GRAY)
        path = root / "reports" / "figures" / "erro_modelos.png"
        fig.savefig(path,dpi=150,facecolor="white")
        plt.close(fig)
    return path


def municipality_swing(root: Path = ROOT) -> pl.DataFrame:
    """Calcula o swing municipal real por votos válidos, sem usar os modelos."""
    yearly = []
    for year in (2022,2026):
        yearly.append(pl.read_parquet(root / "data" / "interim" / f"secoes_{year}.parquet")
                      .filter(pl.col("tem_bu")&(pl.col("uf")!="ZZ"))
                      .group_by("uf","cod_municipio").agg(
                          (pl.col("votos_A").sum()/pl.col("votos_validos").sum()).alias(f"pct_{year}")))
    return yearly[1].join(yearly[0],on=["uf","cod_municipio"],how="inner",validate="1:1").with_columns(
        (100*(pl.col("pct_2026")-pl.col("pct_2022"))).alias("swing_pp"))


def crosswalk(root: Path = ROOT) -> pl.DataFrame:
    """Lê a correspondência oficial 2026 apenas para o mapa descritivo."""
    url = "https://cdn.tse.jus.br/estatistica/sead/odsele/municipio_tse_ibge/municipio_tse_ibge.zip"
    path = download(url,root / "data" / "raw" / "ibge_historico" / "municipio_tse_ibge.zip")
    with zipfile.ZipFile(path) as archive:
        name = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        table = pl.read_csv(io.StringIO(archive.read(name).decode("latin-1")),separator=";",infer_schema=False)
    table = table.select(pl.col("SG_UF").alias("uf"),pl.col("CD_MUNICIPIO_TSE").str.pad_start(5,"0").alias("cod_municipio"),
                         pl.col("CD_MUNICIPIO_IBGE").alias("cod_ibge")).unique()
    table = table.filter(pl.col("cod_ibge").str.contains(r"^\d{7}$")&(pl.col("uf")!="ZZ"))
    if table.select("uf","cod_municipio").is_duplicated().any():
        raise ValueError("Correspondência TSE–IBGE ambígua")
    return table


def municipality_geometry(root: Path = ROOT) -> Any:
    """Obtém a malha geobr com cache e contorna o conversor legado fetchone."""
    import geopandas as gpd

    path = root / "data" / "raw" / "geobr" / "municipios_2022.parquet"
    if not path.exists():
        import geobr

        relation = geobr.read_municipality(year=2022,output="duckdb",show_progress=False,cache=True)
        crs = relation.select("ST_CRS(geometry)").limit(1).fetchall()[0][0]
        rows = relation.select("code_muni, ST_AsWKB(geometry) AS wkb").fetchall()
        geometry = gpd.GeoDataFrame({"code_muni":[int(row[0]) for row in rows]},
                                   geometry=gpd.GeoSeries.from_wkb([bytes(row[1]) for row in rows]),crs=crs)
        path.parent.mkdir(parents=True,exist_ok=True)
        geometry.to_parquet(path)
    return gpd.read_parquet(path)


def swing_map(root: Path = ROOT) -> Path:
    """Desenha o swing municipal com escala simétrica e cobertura documentada."""
    mapped = municipality_swing(root).join(crosswalk(root),on=["uf","cod_municipio"],how="left",validate="1:1")
    usable = mapped.filter(pl.col("cod_ibge").is_not_null()&pl.col("swing_pp").is_finite())
    if usable["cod_ibge"].is_duplicated().any():
        raise ValueError("Mais de um município TSE para a mesma geometria IBGE")
    geometry = municipality_geometry(root)
    geometry["cod_ibge"] = geometry["code_muni"].astype("int64").astype(str).str.zfill(7)
    # Somente a pequena tabela municipal, não CSVs de BU, passa para GeoPandas.
    geography = geometry.merge(usable.select("cod_ibge","swing_pp").to_pandas(),on="cod_ibge",how="left",validate="1:1").to_crs("EPSG:5880")
    limit = max(1,math.ceil(float(usable["swing_pp"].abs().max())))
    cmap = LinearSegmentedColormap.from_list("neutro",["#416C89","#F1F3F5","#80668E"])
    fig,ax = plt.subplots(figsize=(9,9))
    fig.subplots_adjust(top=.85,bottom=.17,left=.02,right=.98)
    geography.plot(column="swing_pp",ax=ax,cmap=cmap,norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit),
                   linewidth=0,missing_kwds={"color":"#D4D8DD","hatch":"///"})
    ax.set_axis_off()
    fig.suptitle("Variação do candidato 13 por município\n2022 → 2026",fontsize=19,weight="bold",y=.96,color="#263F58")
    bar_ax = fig.add_axes([.24,.13,.52,.025])
    scalar = plt.cm.ScalarMappable(norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit),cmap=cmap)
    fig.colorbar(scalar,cax=bar_ax,orientation="horizontal",label="Variação nos votos válidos (p.p.)")
    fig.text(.5,.06,"Descritivo, após as eleições. Cinza/hachura: sem comparação. Exterior não representado.",ha="center",fontsize=9,color=GRAY)
    fig.text(.5,.035,"Fontes: TSE (votos e correspondência de códigos) · geobr/IBGE (malha municipal 2022).",ha="center",fontsize=9,color=GRAY)
    path = root / "reports" / "figures" / "swing_municipios_2022_2026.png"
    fig.savefig(path,dpi=150,facecolor="white")
    plt.close(fig)
    write_json(root / "docs" / "COBERTURA_MAPA.json",{
        "geometria_ano":2022,"municipios_geometria":len(geography),"geometrias_com_swing":int(geography["swing_pp"].notna().sum()),
        "municipios_comparaveis_tse":mapped.height,"sem_depara":mapped.filter(pl.col("cod_ibge").is_null()).height,
        "escala_simetrica_pp":limit,"exterior":"Excluído somente do mapa; mantido nas projeções nacionais.",
        "fonte_depara":"https://dadosabertos.tse.jus.br/dataset/codigos-oficiais-de-uf-e-municipios-segundo-o-tse-e-o-ibge",
        "fonte_geometria":"https://github.com/ipea/geobr","malha":"2022; municípios novos sem comparação não recebem swing inventado."})
    return path


def generate_all(root: Path = ROOT) -> list[Path]:
    """Gera as quatro figuras sem alterar a avaliação ou as calibrações."""
    protected = [root / "data" / "processed" / "avaliacao.parquet",root / "docs" / "CALIBRACAO_IC.json",root / "docs" / "CALIBRACAO_K.json"]
    before = {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    paths = [principal(2026,root),principal(2022,root),errors(root),swing_map(root)]
    if before!={str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}:
        raise ValueError("Geração das figuras alterou o teste ou calibrações")
    write_json(root / "docs" / "FIGURAS_AUDITORIA.json",{
        "faixa":"Estrutural bruta; faixa conservadora, sem cobertura nominal validada.",
        "escolha":"Feita APÓS observar os resultados de 2026; não é uma validação fora da amostra dessa escolha.",
        "arquivos_protegidos_sha256":before,"figuras":[str(path.relative_to(root)) for path in paths]})
    print([str(path) for path in paths],flush=True)
    return paths


if __name__ == "__main__":
    generate_all()
