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
Os resultados de projeção ainda não foram produzidos. A simulação da parcial,
sem estimar votos faltantes, gerou estes resultados nos cortes de 1%:

| Ano | Primeiro corte com erro <1 p.p. | Abaixo de 1 p.p. até o fim | Maior desvio absoluto nos cortes |
| --- | ---: | ---: | ---: |
| 2022 | 62% | 62% | 7,3368 p.p. (em 1%) |
| 2026 | 1% | 66% | 2,3009 p.p. (em 25%) |

Os percentuais estão arredondados. Um erro pequeno no começo não garante que
a parcial permanecerá perto do resultado final. Gráficos: [2022](reports/figures/parcial_2022.png)
e [2026](reports/figures/parcial_2026.png).

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
