# eleicoes-apuracao

## Pergunta

Quem ganha com 30% das urnas apuradas?

O projeto investiga quanto já é possível estimar do resultado final e da
incerteza durante a apuração. As previsões ainda serão avaliadas, incluindo
um backtest de 2022 com base histórica de 2018.

## Dados

Boletins de urna oficiais do TSE de 2018, 2022 e 2026 e indicadores municipais do IBGE.
URLs, colunas reais e limites das fontes estão em [docs/METODO.md](docs/METODO.md)
e [docs/FONTES_IBGE.md](docs/FONTES_IBGE.md).

## Método

O candidato 13 é A nos três anos; B é o candidato 17 em 2018 e o candidato 22
em 2022/2026. A notação serve para comparar proporções e swings. Textos e
gráficos usam números ou nomes de forma neutra, sem cores partidárias carregadas.

**2022 é desenvolvimento/calibração:** k e os fatores dos intervalos são
escolhidos nesse ano. **2026 é teste fora da amostra:** aplica-se a mesma
configuração, sem reajustar pelo resultado do teste. A sequência usada é a
ordem em que os boletins chegaram ao TSE.

Os horários de recebimento de 2022 e 2026 coincidem integralmente com o campo
Hora TSE do detalhe oficial por seção. O método os interpreta como Brasília,
com apoio nas normas eleitorais e na comparação entre UFs; não aplica ajustes
por UF. Há muitos boletins empatados no mesmo segundo, portanto a sequência
de recebimento não determina a ordem dentro desses grupos nem o instante de
divulgação pública. Veja as evidências e limites em [METODO.md](docs/METODO.md).

## Resultados

A ingestão reproduziu exatamente os totais oficiais independentes de votos
por candidato, válidos, brancos, nulos, comparecimento e eleitorado apto.

| Ano | Seções no Parquet | Com BU, para simulação | Sem BU, para conciliação de aptos |
| --- | ---: | ---: | ---: |
| 2018 | 454.490 | 454.448 | 42 |
| 2022 | 472.075 | 472.028 | 47 |
| 2026 | 499.248 | 499.205 | 43 |

As seções sem BU vieram do detalhe oficial, possuem comparecimento e votos
zero e estão marcadas com `tem_bu=False` e `apta_simulacao=False`.
A simulação da parcial, na ordem em que os boletins chegaram ao TSE e sem
estimar votos faltantes, gerou estes resultados nos cortes de 1%:

| Ano | Primeiro corte com erro <1 p.p. | Abaixo de 1 p.p. até o fim | Maior desvio absoluto nos cortes |
| --- | ---: | ---: | ---: |
| 2022 | 62% | 62% | 7,3368 p.p. (em 1%) |
| 2026 | 1% | 66% | 2,3009 p.p. (em 25%) |

Os percentuais estão arredondados. Um erro pequeno no começo não garante que
a parcial permanecerá perto do resultado final. Gráficos: [2022](reports/figures/parcial_2022.png)
e [2026](reports/figures/parcial_2026.png).

Na aferição inicial dos modelos, com 30% das seções de 2022 recebidas, os erros
absolutos foram 1,956 p.p. (M0), 0,688 (M1), 0,432 (M2) e **0,195 (M3)**.
O resultado final do candidato 13 foi 50,9024%; M3 estimou 51,0971%.
Esse corte participou da calibração de k em 2022. No benchmark inicial, o
intervalo do M3, [50,9506%; 51,2413%], não incluiu o resultado final nesse
corte, motivando a revisão do mecanismo de incerteza.

**A avaliação completa não validou os intervalos em 2026.** Após acrescentar
choques comuns e calibrar a escala exclusivamente em 2022, as coberturas no
teste de 2026 foram 19,19% (M1), 7,07% (M2) e **6,06% (M3)**, longe dos 90%
pretendidos. Em 2022, os três atingem 90,91% por construção. Não houve
reajuste dos fatores usando 2026; não se deve anunciar cobertura de 90% validada.

A projeção pontual do M3 manteve o vencedor correto desde o corte de 1% em
2026, uma estabilidade retrospectiva que não equivale a certeza estatística.
Foram avaliados 99 cortes por ano, em 52,31 minutos. O relatório completo,
incluindo erros em 10/30/50%, está em [RESULTADOS.md](docs/RESULTADOS.md).

Os testes zeram e removem os resultados das seções faltantes para garantir
que os modelos usem apenas informações disponíveis no snapshot. Fontes e
limites estão em [METODO.md](docs/METODO.md); os tempos e os quatro cortes
por ano estão em [BENCHMARK_MODELOS.json](docs/BENCHMARK_MODELOS.json).

O pareamento por seção ou local de votação cobre **98,9102% dos aptos de 2022**
(base 2018) e **97,6169% dos aptos de 2026** (base 2022). Os demais usam zona,
município ou UF. Essas coberturas medem disponibilidade da base histórica;
a precisão das projeções será medida no backtest.

## Como rodar

Com Python 3.12 e uv instalados, na raiz do projeto:

```powershell
uv sync
uv run python -m apuracao.download --ano 2026
uv run python -m apuracao.download --ano 2022
uv run python -m apuracao.download --ano 2018
uv run python -m apuracao.ingest
uv run python -m apuracao.match
uv run python -m apuracao.simulate
uv run python -m apuracao.features
uv run python -m apuracao.models --calibrar-k
uv run python -m apuracao.evaluate --workers 4 --n-jobs 1
uv run pytest
```

Cada chamada baixa o último turno publicado do ano escolhido, incluindo exterior,
e as fontes do IBGE. As pastas `data/raw`, `data/interim` e `data/processed` são
criadas automaticamente. O cache evita novos downloads de arquivos existentes;
os ZIPs são mantidos compactados e conferidos com SHA-512 oficial do TSE.
O catálogo também é armazenado em cache: as URLs usadas ficam nos manifestos.
Uma falha HTTP, de JSON ou de integridade interrompe a execução para inspeção.

Os dados ficam fora do Git. A ingestão baixa também as fontes oficiais de
conferência e gera `data/interim/secoes_{ano}.parquet`. Para um único ano,
use `uv run python -m apuracao.ingest --ano 2026`. O DuckDB instala a extensão
oficial `encodings` no primeiro uso e a reutiliza do cache. Evidências de
validação ficam versionadas em [VALIDACAO_INGESTAO.json](docs/VALIDACAO_INGESTAO.json).
