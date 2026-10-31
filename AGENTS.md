# Regras do projeto

- Toda lógica fica em `src/apuracao/`; notebooks apenas importam e chamam funções.
- Dados grandes: ler com DuckDB/Polars; nunca carregar CSV inteiro do TSE no pandas.
- Salvar intermediários em Parquet em `data/interim/` e `data/processed/`.
- CSVs do TSE: encoding `latin-1`, separador `;`.
- Downloads idempotentes com cache em `data/raw/`: não baixar de novo se o arquivo existir.
- Funções com type hints e docstring curta em português.
- Rodar `uv run pytest` antes de terminar qualquer tarefa.
- Não inventar nomes de colunas: inspecionar o arquivo real e documentar em `docs/METODO.md`.
