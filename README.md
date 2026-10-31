# eleicoes-apuracao

## Pergunta

## Dados

Boletins de urna oficiais do TSE de 2018, 2022 e 2026 e indicadores municipais do IBGE.
URLs, colunas reais e limites das fontes estão em [docs/METODO.md](docs/METODO.md)
e [docs/FONTES_IBGE.md](docs/FONTES_IBGE.md).

## Método

## Resultados

## Como rodar

Com Python 3.12 e uv instalados, na raiz do projeto:

```powershell
uv sync
uv run python -m apuracao.download --ano 2026
uv run python -m apuracao.download --ano 2022
uv run python -m apuracao.download --ano 2018
uv run pytest
```

Cada chamada baixa o último turno publicado do ano escolhido, incluindo exterior,
e as fontes do IBGE. As pastas `data/raw`, `data/interim` e `data/processed` são
criadas automaticamente. O cache evita novos downloads de arquivos existentes;
os ZIPs são mantidos compactados e conferidos com SHA-512 oficial do TSE.
O catálogo também é armazenado em cache: as URLs usadas ficam nos manifestos.
Uma falha HTTP, de JSON ou de integridade interrompe a execução para inspeção.

Os dados ficam fora do Git. Esta etapa apenas baixa e inspeciona amostras; ainda
não gera dados tratados. A inspeção atual identifica horário de recebimento nos
BUs de 2022 e 2026; em 2018 o campo está ausente.
