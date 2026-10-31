# Método

## Prompt 2: confirmação dos candidatos (etapa parcial)

Leitura integral dos 84 CSVs de BU usando DuckDB, um arquivo por vez, após
descompactação temporária. A extensão oficial `encodings` é instalada em cache
na primeira execução para ler `latin-1`. Os arquivos temporários são apagados.
O filtro exige `CD_CARGO_PERGUNTA = 1`, `DS_CARGO_PERGUNTA = Presidente`,
`NR_TURNO = 2` e `DS_TIPO_VOTAVEL = Nominal` (descrições sem distinção de caixa).
A consulta lista valores distintos, sem somar aptos, comparecimento ou votos.
Todos os arquivos de cada ano, inclusive `ZZ`, foram consultados.

| Ano | NR_VOTAVEL | NM_VOTAVEL | SG_PARTIDO |
| --- | --- | --- | --- |
| 2018 | 13 | FERNANDO HADDAD | PT |
| 2018 | 17 | JAIR BOLSONARO | PSL |
| 2022 | 13 | LULA | PT |
| 2022 | 22 | JAIR BOLSONARO | PL |
| 2026 | 13 | LULA | PT |
| 2026 | 22 | FLAVIO BOLSONARO | PL |

Comando: `uv run python -m apuracao.ingest --listar-candidatos`.
O mapeamento A/B aguarda confirmação do usuário e não foi criado.
Esta etapa ainda não gera `secoes_{ano}.parquet`. Permanecem pendentes a
agregação por seção, a investigação de fuso horário, o relatório de nulos e
empates, as seções agregadas e a comparação de totais com fonte independente.
A existência de horário de recebimento ainda não resolve a comparação entre
fusos nem estabelece o instante de totalização pública.

<!-- inicio:inspecao-download -->
## Inspeção dos boletins de urna (Prompt 1)

CSV lido diretamente do ZIP, com encoding `latin-1` e separador `;`. Foram lidos o cabeçalho e três registros por CSV; não houve ingestão, filtragem de presidente, soma de votos ou geração de Parquet.

Os manifestos completos e amostras ficam em `data/raw/tse/{ano}/manifesto.json`. Cada ZIP foi comparado com o SHA-512 publicado pelo TSE. Os dados brutos permanecem fora do Git.

### Horário de recebimento

| Ano | Turno publicado selecionado | CSVs inspecionados | Campo | Exemplo real (AC) |
| --- | --- | --- | --- | --- |
| 2018 | 2 | 28 | ausente (0/28) | `ausente` |
| 2022 | 2 | 28 | DT_BU_RECEBIDO (28/28) | `30/10/2022 17:34:43` |
| 2026 | 2 | 28 | DT_BU_RECEBIDO (28/28) | `2026-10-25 19:42:19` |

Em 2022, `DT_BU_RECEBIDO` usa `DD/MM/AAAA HH:MM:SS`; em 2026, `AAAA-MM-DD HH:MM:SS`. A inspeção confirma o campo nos 28 cabeçalhos de cada um desses anos, mas as amostras não demonstram cobertura integral dos valores. Os valores não trazem offset de fuso horário. Na ingestão, verificar nulos, sentinelas, fusos e empates antes de reconstruir a sequência nacional.

Para os snapshots de 2026 e o backtest de 2022, há evidência para ordenar pelo recebimento registrado do BU, após essas verificações. Isso não demonstra o instante em que o voto entrou na totalização pública. Em 2018, o campo não existe: a ordem seria simulada se esse ano fosse usado como alvo de apuração. Como base do backtest de 2022, 2018 não precisa dessa ordem.

`DT_GERACAO`/`HH_GERACAO` referem-se à geração do arquivo; `DT_ABERTURA`, `DT_ENCERRAMENTO` e `DT_EMISSAO_BU` não substituem o recebimento.

### Colunas reais

Os cabeçalhos abaixo preservam a grafia original. Em 2018 há `SG_ UF` (com espaço) e `CD_FLASCARD_URNA_EFETIVADA`. `CD_MUNICIPIO` é a chave do TSE e não deve ser confundida com a chave IBGE. O arquivo contém múltiplos cargos e múltiplas linhas por seção; a seleção de presidente será feita no Prompt 2.

#### 2018

Fonte: [catálogo oficial](https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2018-boletim-de-urna).

Cabeçalho observado em 28 CSVs (42 colunas):

```text
DT_GERACAO;HH_GERACAO;ANO_ELEICAO;CD_PLEITO;DT_PLEITO;NR_TURNO;CD_ELEICAO;DS_ELEICAO;DT_ELEICAO;SG_ UF;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;NR_SECAO;NR_LOCAL_VOTACAO;CD_CARGO_PERGUNTA;DS_CARGO_PERGUNTA;NR_PARTIDO;SG_PARTIDO;NM_PARTIDO;QT_APTOS;QT_COMPARECIMENTO;QT_ABSTENCOES;CD_TIPO_URNA;DS_TIPO_URNA;CD_TIPO_VOTAVEL;DS_TIPO_VOTAVEL;NR_VOTAVEL;NM_VOTAVEL;QT_VOTOS;NR_URNA_EFETIVADA;CD_CARGA_1_URNA_EFETIVADA;CD_CARGA_2_URNA_EFETIVADA;CD_FLASCARD_URNA_EFETIVADA;DT_CARGA_URNA_EFETIVADA;DS_CARGO_PERGUNTA_SECAO;DS_AGREGADAS;DT_ABERTURA;DT_ENCERRAMENTO;QT_ELEITORES_BIOMETRIA_NH;NR_JUNTA_APURADORA;NR_TURMA_APURADORA
```

| UF | ZIP oficial | Bytes |
| --- | --- | --- |
| AC | [BWEB_2t_AC_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_AC_301020181744.zip) | 477427 |
| AL | [BWEB_2t_AL_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_AL_301020181744.zip) | 877133 |
| AM | [BWEB_2t_AM_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_AM_301020181744.zip) | 1559466 |
| AP | [BWEB_2t_AP_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_AP_301020181744.zip) | 605450 |
| BA | [BWEB_2t_BA_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_BA_301020181744.zip) | 3117790 |
| CE | [BWEB_2t_CE_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_CE_301020181744.zip) | 2251510 |
| DF | [BWEB_2t_DF_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_DF_301020181744.zip) | 1524675 |
| ES | [BWEB_2t_ES_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_ES_301020181744.zip) | 1088824 |
| GO | [BWEB_2t_GO_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_GO_301020181744.zip) | 1569917 |
| MA | [BWEB_2t_MA_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_MA_301020181744.zip) | 1725548 |
| MG | [BWEB_2t_MG_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_MG_301020181744.zip) | 8926694 |
| MS | [BWEB_2t_MS_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_MS_301020181744.zip) | 1471088 |
| MT | [BWEB_2t_MT_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_MT_301020181744.zip) | 949104 |
| PA | [BWEB_2t_PA_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_PA_301020181744.zip) | 3367242 |
| PB | [BWEB_2t_PB_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_PB_301020181744.zip) | 1199622 |
| PE | [BWEB_2t_PE_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_PE_301020181744.zip) | 2074761 |
| PI | [BWEB_2t_PI_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_PI_301020181744.zip) | 1108347 |
| PR | [BWEB_2t_PR_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_PR_301020181744.zip) | 2652967 |
| RJ | [BWEB_2t_RJ_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_RJ_301020181744.zip) | 6488942 |
| RN | [BWEB_2t_RN_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_RN_301020181744.zip) | 1640857 |
| RO | [BWEB_2t_RO_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_RO_301020181744.zip) | 1058933 |
| RR | [BWEB_2t_RR_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_RR_301020181744.zip) | 516876 |
| RS | [BWEB_2t_RS_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_RS_301020181744.zip) | 5321281 |
| SC | [BWEB_2t_SC_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_SC_301020181744.zip) | 3106315 |
| SE | [BWEB_2t_SE_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_SE_301020181744.zip) | 1242173 |
| SP | [BWEB_2t_SP_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_SP_301020181744.zip) | 17587277 |
| TO | [BWEB_2t_TO_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_TO_301020181744.zip) | 649734 |
| ZZ | [BWEB_2t_ZZ_301020181744.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2018/buweb/BWEB_2t_ZZ_301020181744.zip) | 376323 |

#### 2022

Fonte: [catálogo oficial](https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2022-boletim-de-urna).

Cabeçalho observado em 28 CSVs (45 colunas):

```text
DT_GERACAO;HH_GERACAO;ANO_ELEICAO;CD_TIPO_ELEICAO;NM_TIPO_ELEICAO;CD_PLEITO;DT_PLEITO;NR_TURNO;CD_ELEICAO;DS_ELEICAO;SG_UF;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;NR_SECAO;NR_LOCAL_VOTACAO;CD_CARGO_PERGUNTA;DS_CARGO_PERGUNTA;NR_PARTIDO;SG_PARTIDO;NM_PARTIDO;DT_BU_RECEBIDO;QT_APTOS;QT_COMPARECIMENTO;QT_ABSTENCOES;CD_TIPO_URNA;DS_TIPO_URNA;CD_TIPO_VOTAVEL;DS_TIPO_VOTAVEL;NR_VOTAVEL;NM_VOTAVEL;QT_VOTOS;NR_URNA_EFETIVADA;CD_CARGA_1_URNA_EFETIVADA;CD_CARGA_2_URNA_EFETIVADA;CD_FLASHCARD_URNA_EFETIVADA;DT_CARGA_URNA_EFETIVADA;DS_CARGO_PERGUNTA_SECAO;DS_AGREGADAS;DT_ABERTURA;DT_ENCERRAMENTO;QT_ELEITORES_BIOMETRIA_NH;DT_EMISSAO_BU;NR_JUNTA_APURADORA;NR_TURMA_APURADORA
```

| UF | ZIP oficial | Bytes |
| --- | --- | --- |
| AC | [bweb_2t_AC_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_AC_311020221535.zip) | 538139 |
| AL | [bweb_2t_AL_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_AL_311020221535.zip) | 1341316 |
| AM | [bweb_2t_AM_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_AM_311020221535.zip) | 1480749 |
| AP | [bweb_2t_AP_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_AP_311020221535.zip) | 501229 |
| BA | [bweb_2t_BA_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_BA_311020221535.zip) | 5522366 |
| CE | [bweb_2t_CE_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_CE_311020221535.zip) | 2613744 |
| DF | [bweb_2t_DF_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_DF_311020221535.zip) | 998403 |
| ES | [bweb_2t_ES_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_ES_311020221535.zip) | 1717142 |
| GO | [bweb_2t_GO_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_GO_311020221535.zip) | 1786175 |
| MA | [bweb_2t_MA_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_MA_311020221535.zip) | 1965703 |
| MG | [bweb_2t_MG_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_MG_311020221535.zip) | 5283911 |
| MS | [bweb_2t_MS_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_MS_311020221535.zip) | 1380373 |
| MT | [bweb_2t_MT_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_MT_311020221535.zip) | 1081503 |
| PA | [bweb_2t_PA_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_PA_311020221535.zip) | 2118855 |
| PB | [bweb_2t_PB_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_PB_311020221535.zip) | 1806259 |
| PE | [bweb_2t_PE_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_PE_311020221535.zip) | 3469891 |
| PI | [bweb_2t_PI_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_PI_311020221535.zip) | 1227487 |
| PR | [bweb_2t_PR_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_PR_311020221535.zip) | 2855742 |
| RJ | [bweb_2t_RJ_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_RJ_311020221535.zip) | 3728044 |
| RN | [bweb_2t_RN_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_RN_311020221535.zip) | 1090336 |
| RO | [bweb_2t_RO_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_RO_311020221535.zip) | 959055 |
| RR | [bweb_2t_RR_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_RR_311020221535.zip) | 450233 |
| RS | [bweb_2t_RS_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_RS_311020221535.zip) | 4537987 |
| SC | [bweb_2t_SC_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_SC_311020221535.zip) | 2776735 |
| SE | [bweb_2t_SE_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_SE_311020221535.zip) | 1168873 |
| SP | [bweb_2t_SP_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_SP_311020221535.zip) | 16096583 |
| TO | [bweb_2t_TO_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_TO_311020221535.zip) | 721111 |
| ZZ | [bweb_2t_ZZ_311020221535.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/buweb/bweb_2t_ZZ_311020221535.zip) | 433558 |

#### 2026

Fonte: [catálogo oficial](https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2026-boletim-de-urna).

Cabeçalho observado em 28 CSVs (45 colunas):

```text
DT_GERACAO;HH_GERACAO;ANO_ELEICAO;CD_TIPO_ELEICAO;NM_TIPO_ELEICAO;CD_PLEITO;DT_PLEITO;NR_TURNO;CD_ELEICAO;DS_ELEICAO;SG_UF;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;NR_SECAO;NR_LOCAL_VOTACAO;CD_CARGO_PERGUNTA;DS_CARGO_PERGUNTA;NR_PARTIDO;SG_PARTIDO;NM_PARTIDO;DT_BU_RECEBIDO;QT_APTOS;QT_COMPARECIMENTO;QT_ABSTENCOES;CD_TIPO_URNA;DS_TIPO_URNA;CD_TIPO_VOTAVEL;DS_TIPO_VOTAVEL;NR_VOTAVEL;NM_VOTAVEL;QT_VOTOS;NR_URNA_EFETIVADA;CD_CARGA_1_URNA_EFETIVADA;CD_CARGA_2_URNA_EFETIVADA;CD_FLASHCARD_URNA_EFETIVADA;DT_CARGA_URNA_EFETIVADA;DS_CARGO_PERGUNTA_SECAO;DS_SECOES_AGREGADAS;DT_ABERTURA;DT_ENCERRAMENTO;QT_ELEI_BIOM_SEM_HABILITACAO;DT_EMISSAO_BU;NR_JUNTA_APURADORA;NR_TURMA_APURADORA
```

| UF | ZIP oficial | Bytes |
| --- | --- | --- |
| AC | [bweb_2t_AC_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_AC_261020260742.zip) | 1254611 |
| AL | [bweb_2t_AL_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_AL_261020260742.zip) | 1945168 |
| AM | [bweb_2t_AM_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_AM_261020260742.zip) | 4276454 |
| AP | [bweb_2t_AP_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_AP_261020260742.zip) | 596704 |
| BA | [bweb_2t_BA_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_BA_261020260742.zip) | 9513048 |
| CE | [bweb_2t_CE_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_CE_261020260742.zip) | 6151144 |
| DF | [bweb_2t_DF_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_DF_261020260742.zip) | 3846786 |
| ES | [bweb_2t_ES_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_ES_261020260742.zip) | 5275706 |
| GO | [bweb_2t_GO_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_GO_261020260742.zip) | 4248869 |
| MA | [bweb_2t_MA_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_MA_261020260742.zip) | 4609442 |
| MG | [bweb_2t_MG_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_MG_261020260742.zip) | 14071007 |
| MS | [bweb_2t_MS_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_MS_261020260742.zip) | 1863398 |
| MT | [bweb_2t_MT_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_MT_261020260742.zip) | 2204666 |
| PA | [bweb_2t_PA_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_PA_261020260742.zip) | 5158441 |
| PB | [bweb_2t_PB_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_PB_261020260742.zip) | 2871353 |
| PE | [bweb_2t_PE_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_PE_261020260742.zip) | 5761723 |
| PI | [bweb_2t_PI_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_PI_261020260742.zip) | 2648710 |
| PR | [bweb_2t_PR_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_PR_261020260742.zip) | 7189112 |
| RJ | [bweb_2t_RJ_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_RJ_261020260742.zip) | 10004912 |
| RN | [bweb_2t_RN_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_RN_261020260742.zip) | 4424654 |
| RO | [bweb_2t_RO_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_RO_261020260742.zip) | 1250142 |
| RR | [bweb_2t_RR_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_RR_261020260742.zip) | 500520 |
| RS | [bweb_2t_RS_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_RS_261020260742.zip) | 7410270 |
| SC | [bweb_2t_SC_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_SC_261020260742.zip) | 4487185 |
| SE | [bweb_2t_SE_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_SE_261020260742.zip) | 1645477 |
| SP | [bweb_2t_SP_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_SP_261020260742.zip) | 28188300 |
| TO | [bweb_2t_TO_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_TO_261020260742.zip) | 2383586 |
| ZZ | [bweb_2t_ZZ_261020260742.zip](https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_ZZ_261020260742.zip) | 502322 |

### IBGE e limites desta etapa

Fontes, variáveis, unidades, períodos e restrições estão em [FONTES_IBGE.md](FONTES_IBGE.md). As respostas SIDRA brutas incluem população do Censo 2022, estimativa 2026, PIB total 2023, taxa de alfabetização 2022 e renda domiciliar per capita 2022. PIB per capita foi baixado na base oficial TXT 2010–2023, com layout PDF no mesmo ZIP: a API consultada foi bloqueada neste ambiente. Esse é um desvio explícito do pedido de usar API para todos os indicadores. Não se confundiu PIB total com PIB per capita.

As amostras e URLs IBGE estão em `data/raw/ibge/manifesto.json`. Não houve cálculo de indicadores. Antes de modelar cada eleição, selecionar dados publicados até a data simulada, especialmente no backtest de 2022; indicadores de anos posteriores não podem entrar nas previsões históricas.

<!-- fim:inspecao-download -->
