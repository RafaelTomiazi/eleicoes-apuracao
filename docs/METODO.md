# Método

## Prompt 2: candidatos confirmados

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
O usuário confirmou A=13 nos três anos; B=17 em 2018 e B=22 em 2022/2026.
Configuração em `src/apuracao/config.py`. Justificativa confirmada:
"13 é o único número presente nos três anos; num 2º turno %B = 100 - %A,
então a escolha só define o sinal do swing, não altera projeções nem erros."
A invariância pressupõe modelos e intervalos transformados de forma equivalente
ao trocar A/B; a configuração não afirma equivalência ideológica entre candidatos.

### Agregação e esquema dos Parquets

Comando completo: `uv run python -m apuracao.ingest` ou `--ano 2026`.
As 28 UFs de cada ano, inclusive exterior `ZZ`, são lidas com DuckDB.
`QT_APTOS`, `QT_COMPARECIMENTO`, `QT_ABSTENCOES`, horário e agregadas usam
`max` somente após recusar valores repetidos divergentes na mesma seção.
`QT_VOTOS` é somado por tipo e número do votável; somente Nominal, Branco e
Nulo foram observados. Se aparecer outro tipo ou candidato, a ingestão falha.
Confere-se o balanço válidos+brancos+nulos=comparecimento e
comparecimento+abstenções=aptos em cada seção. Chaves duplicadas são recusadas.

A chave é `(uf, cod_municipio, zona, secao)`. O código municipal TSE fica como
texto de cinco dígitos, inclusive zeros iniciais; zona e seção são inteiros.
`SG_ UF` é normalizada para `uf`; `DS_AGREGADAS` e `DS_SECOES_AGREGADAS` para
`secoes_agregadas`; `CD_FLASCARD_URNA_EFETIVADA` e
`CD_FLASHCARD_URNA_EFETIVADA` para `cd_flashcard_urna_efetivada`.
O texto de seções agregadas é preservado e não explode em linhas adicionais:
os votos e eleitores já pertencem à seção principal da urna.

Saídas: `data/interim/secoes_{ano}.parquet`, com `uf`, `cod_municipio`,
`nome_municipio`, `zona`, `secao`, `local_votacao`, `aptos`, `comparecimento`, `abstencoes`,
`votos_A`, `votos_B`, `votos_validos`, `brancos`, `nulos`, `votos_por_numero`
(mapa número -> votos), `votos_13` e `votos_17`/`votos_22`, `recebido_texto`,
`recebido_em_registrado`, `recebido_em`, `emitido_em_registrado`,
`encerramento_registrado`, `secoes_agregadas`, `cd_flashcard_urna_efetivada`,
`exterior`, `tem_bu`, `apta_simulacao`, `origem_registro`,
`situacao_instalada_oficial`, `situacao_anulada_oficial`, `recebido_hor_tse_oficial`.

### Cobertura e totalização independente

Foram baixados do [catálogo oficial TSE](https://dadosabertos.tse.jus.br/dataset/)
os ZIPs `votacao_candidato_munzona_{ano}`, `detalhe_votacao_munzona_{ano}` e
`detalhe_votacao_secao_{ano}`. Usou-se somente `*_{ano}_BR.csv`, com cargo 1,
turno 2 e unidade eleitoral BR. Não se concatenou BR com BRASIL ou UFs,
pois haveria duplicação. URLs exatas, cabeçalhos inspecionados, registros ausentes
e resultados estão em [VALIDACAO_INGESTAO.json](VALIDACAO_INGESTAO.json).

Campos usados na votação nominal: `NR_CANDIDATO`, `QT_VOTOS_NOMINAIS_VALIDOS`.
No detalhe municipal: `QT_APTOS`, `QT_COMPARECIMENTO`, `QT_TOTAL_VOTOS_VALIDOS`,
`QT_VOTOS_BRANCOS`, `QT_TOTAL_VOTOS_NULOS`, `QT_ELEITORES_SECOES_NAO_INSTALADAS`,
`QT_SECOES_PRINCIPAIS`, `QT_SECOES_AGREGADAS`, `QT_SECOES_NAO_INSTALADAS`.
No detalhe por seção: chaves `SG_UF`, `CD_MUNICIPIO`, `NR_ZONA`, `NR_SECAO`;
`QT_APTOS`, `QT_COMPARECIMENTO`, `QT_VOTOS_NOMINAIS`, `QT_VOTOS_BRANCOS`,
`QT_VOTOS_NULOS`, `ST_SECAO_INSTALADA`, `ST_SECAO_ANULADA`, `DS_ORIGEM_VOTO`,
`DT_RECEBIMENTO_BU_HOR_TSE`. Os cabeçalhos completos estão no JSON versionado.

O eleitorado nacional inclui seções sem BU. Elas foram identificadas por
anti-join com o detalhe oficial por seção, nunca pelo resíduo dos totais.
Todos os seus comparecimentos e votos são zero na fonte independente.
Essas linhas recebem `tem_bu=False`, `apta_simulacao=False`,
`origem_registro=detalhe_oficial_sem_bu`, horário do BU nulo e aptos da fonte
oficial. O horário administrativo do detalhe fica em campo separado e não é
inventado como chegada de um BU. Nas seções com BU, aptos e comparecimento
são confrontados individualmente com a fonte independente antes da publicação.

| Ano | Linhas no Parquet | Com BU / aptas à simulação | Sem BU | Aptos sem BU |
| --- | ---: | ---: | ---: | ---: |
| 2018 | 454.490 | 454.448 | 42 | 1.139 |
| 2022 | 472.075 | 472.028 | 47 | 657 |
| 2026 | 499.248 | 499.205 | 43 | 525 |

Em 2018 há 40 seções não instaladas com 470 aptos e duas outras sem BU,
ES/56227/zona37/seção87 (334 aptos) e PR/78573/zona83/seção15 (335 aptos).
O detalhe de 2018 não informa a situação dessas duas; não foram rotuladas
como não instaladas. Em 2026 são 41 não instaladas (423 aptos) e duas outras
sem BU (102 aptos); os indicadores de situação originais ficam no JSON.
Em 2022, as 47 sem BU correspondem às 47 não instaladas. Não confundir o
número de seções principais com o de seções agregadas.

| Ano | Aptos | Votos candidato 13 | Votos outro candidato | Válidos | Diferença contra fonte |
| --- | ---: | ---: | ---: | ---: | --- |
| 2018 | 147.306.294 | 47.040.906 | 57.797.847 (17) | 104.838.753 | zero em todos |
| 2022 | 156.454.011 | 60.345.999 | 58.206.354 (22) | 118.552.353 | zero em todos |
| 2026 | 158.745.502 | 64.256.232 | 59.826.041 (22) | 124.082.273 | zero em todos |

Comparecimento, brancos e nulos também coincidem exatamente. Os totais fixos
de referência estão em `config.py`, com fontes; a rotina e os testes leem
também os totais obtidos dos arquivos independentes, sem derivá-los dos BUs.
Os testes reais são pulados se o clone não tiver os dados locais; neste ambiente
os três anos foram executados. Há também testes sintéticos para atributos
repetidos, conflitos e diferenças históricas do cabeçalho.

### Fuso e limites da ordem de recebimento

**Conclusão operacional: `DT_BU_RECEBIDO` já usa o relógio do TSE, interpretado
como Brasília em 2022 e 2026. Não somar horas por UF.** A associação a Brasília
é uma inferência documentada, não uma definição literal no dicionário BWEB.
O leiame do detalhe por seção identifica `DT_RECEBIMENTO_BU_HOR_TSE` como Hora
TSE. O confronto por chave encontrou igualdade de timestamp em **472.028 de
472.028 BUs de 2022 e 499.205 de 499.205 BUs de 2026**, inclusive exterior.
A [Resolução 23.669/2021, art. 254](https://www.tse.jus.br/legislacao/compilada/res/2021/resolucao-no-23-669-de-14-de-dezembro-de-2021)
estabelece o horário de Brasília para as UFs em 2022; a
[Resolução 23.751/2026, art. 282](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-751-de-26-de-fevereiro-de-2026)
abrange da abertura das seções à divulgação dos resultados em 2026.

Primeiro recebimento por UF no dia do segundo turno:

| Ano | AC | AM | MT | DF |
| --- | --- | --- | --- | --- |
| 2022 | 17:10:07 | 17:03:49 | 17:05:24 | 17:02:09 |
| 2026 | 17:05:10 | 17:05:10 | 17:05:10 | 17:05:10 |

Os encerramentos registrados nas urnas começam perto de 15h no AC, 15h/16h no
AM, 16h no MT e 17h no DF. O AM abrange mais de um fuso e `ZZ` abrange muitos:
não se pode converter horários locais usando apenas a UF.
`recebido_texto` e `recebido_em_registrado` preservam o dado original;
`recebido_em` é `TIMESTAMP WITH TIME ZONE`, com interpretação
`America/Sao_Paulo` (UTC-3 nas datas de 2022/2026). O instante pode aparecer
em UTC em leitores de Parquet; convertê-lo para Brasília na exibição.
2018 mantém `recebido_em` nulo: o campo falta no BU. Embora o detalhe oficial
possua horários de 2018, eles não foram misturados ao horário de BU.

Nos BUs de 2022/2026: zero horários nulos, zero sentinelas, zero inválidos.
Em 2018, os 454.448 BUs não têm esse campo. As linhas suplementares sem BU
têm horário nulo por construção e não participam da simulação.

| Ano | Instantes com empate | Seções em empates | Maior grupo no mesmo segundo |
| --- | ---: | ---: | ---: |
| 2022 | 9.773 | 470.413 | 379 |
| 2026 | 3.985 | 498.344 | 402 |

Um timestamp de segundo não permite recuperar a ordem dentro dos empates.
No Prompt 4, desempatar de forma determinística por
`(uf, cod_municipio, zona, secao)`. Não chamar essa sequência de
ordem exata de divulgação pública: recebimento, processamento e publicação
são instantes distintos. Os horários de encerramento também têm anomalias
pontuais; não foram usados para alterar automaticamente timestamps de chegada.

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

## Regras do pareamento e da simulação

Antes do pareamento, os três Parquets foram regenerados com
`NR_LOCAL_VOTACAO` dos BUs normalizado como `local_votacao` (inteiro), usando
`max` após verificar consistência das repetições por seção. Na suplementação
sem BU, usa-se a coluna homônima do detalhe oficial por seção. Sentinelas
conhecidas do BU tornam-se nulas e nunca formam um local fictício para junção.
Os testes de totais independentes continuam exigindo igualdade exata.

Comando: `uv run python -m apuracao.match`, ou `--ano 2026`.
Saídas: `data/processed/pareado_2022.parquet` e `pareado_2026.parquet`.
O pareamento usa somente dados do TSE; nenhuma tabela ou chave IBGE é usada.
Somente `tem_bu=True` entra no alvo e nas estatísticas históricas.

A cascata escolhe o primeiro nível com votos válidos e aptos positivos:

1. `secao`: `(uf, cod_municipio, zona, secao)`.
2. `local`: `(uf, cod_municipio, zona, local_votacao)`.
3. `zona`: `(uf, cod_municipio, zona)`.
4. `municipio`: `(uf, cod_municipio)`.
5. `uf`: `uf`, incluindo `ZZ` para exterior e códigos municipais ausentes na base.

Em cada grupo, `pct_A_base = sum(votos_A) / sum(votos_A + votos_B)` e
`comparec_base = sum(comparecimento) / sum(aptos)`, calculados **apenas na base**.
São frações entre 0 e 1, não percentuais entre 0 e 100. A primeira taxa é
ponderada pelos votos válidos, e a segunda pelos aptos; não há média simples
dos percentuais por seção. Grupos sem denominador válido são pulados.
Se nem a UF tiver base válida, a execução falha sem inventar média nacional.
Chaves de seção duplicadas são recusadas para impedir multiplicação de linhas.

O resultado preserva as colunas do alvo e acrescenta `pct_A_base`,
`comparec_base`, `nivel_pareamento`, `pareada` (verdadeira somente no nível
`secao`), `ano_base`, `secoes_base_no_grupo`, `votos_validos_base_no_grupo` e
`aptos_base_no_grupo`. Votos do alvo são preservados para avaliação posterior,
mas não entram no cálculo dessas características históricas.

### Seções agregadas e identidade entre anos

Exemplos reais de `secoes_agregadas`: `0419`, `0084 / 0086` em 2018 e
`84 / 109` em 2022. O texto é preservado; cada BU representa a seção principal
com o total da urna. Os membros agregados não viram linhas históricas extras,
pois isso repetiria votos e aptos.

Se uma seção alvo existia apenas como membro de uma agregação na base, não
há registro autônomo para o nível `secao`: ela segue para `local`, e depois
zona/município/UF se necessário. As taxas desses grupos incluem os votos da
principal uma única vez. Não se divide o BU da principal entre membros nem se
afirma conhecer os votos individuais de cada agregada. Se a principal existe
com a mesma chave nos dois anos, vale a regra de seção, mesmo quando a
composição da agregação mudou. Portanto, igualdade de chave é uma aproximação
administrativa e não prova que o eleitorado ou a escola permaneceram iguais.
Um código de local também pode ser alterado, caso em que a cascata segue para
os níveis mais amplos. Essa limitação deve acompanhar a interpretação do swing.

### Regras confirmadas para o Prompt 4

- Denominador de `% apurado`: número de seções do **ano alvo com `tem_bu=True`**.
  Não contar as linhas suplementares sem BU e não ponderar esse percentual por aptos.
- Ordenação: `recebido_em`, depois `(uf, cod_municipio, zona, secao)` para empates.
  `cod_municipio` é o código TSE de cinco dígitos; zona e seção são inteiros.
- `ZZ` participa do denominador e da ordenação pelo horário do TSE, sem ajuste
  para um suposto fuso único do exterior.
- A ordem dentro de um segundo empatado é convencional e reproduzível.
  Os snapshots de 1% podem cortar esses grupos; isso não representa uma ordem
  observada de publicação pública.

O teste exige seção + local **estritamente acima de 90% dos aptos do alvo**.
O relatório é impresso e salvo antes dessa verificação; se a meta falhar, o
Parquet daquele pareamento não é publicado e a execução para para revisão.
As evidências estão em [COBERTURA_PAREAMENTO.json](COBERTURA_PAREAMENTO.json).

<!-- inicio:cobertura-pareamento -->
## Cobertura do pareamento (Prompt 3)

Denominador: apenas seções com `tem_bu=True` e seus aptos no ano alvo. As proporções históricas usam apenas BUs do ano base.

| Alvo ← base | Nível | Seções | % seções | Aptos | % aptos |
| --- | --- | ---: | ---: | ---: | ---: |
| 2022 ← 2018 | secao | 437833 | 92.7557 | 146354651 | 93.5452 |
| 2022 ← 2018 | local | 28310 | 5.9975 | 8393671 | 5.3650 |
| 2022 ← 2018 | zona | 4833 | 1.0239 | 1397527 | 0.8933 |
| 2022 ← 2018 | municipio | 1048 | 0.2220 | 307312 | 0.1964 |
| 2022 ← 2018 | uf | 4 | 0.0008 | 193 | 0.0001 |
| 2026 ← 2022 | secao | 461219 | 92.3907 | 148018168 | 93.2427 |
| 2026 ← 2022 | local | 25177 | 5.0434 | 6943786 | 4.3742 |
| 2026 ← 2022 | zona | 10600 | 2.1234 | 3029698 | 1.9085 |
| 2026 ← 2022 | municipio | 2148 | 0.4303 | 714576 | 0.4501 |
| 2026 ← 2022 | uf | 61 | 0.0122 | 38749 | 0.0244 |

Seção + local em 2022: **98.9102% dos aptos**; meta estrita >90%: aprovada.


Seção + local em 2026: **97.6169% dos aptos**; meta estrita >90%: aprovada.

<!-- fim:cobertura-pareamento -->

## Implementação dos snapshots

Comando: `uv run python -m apuracao.simulate` (2022 e 2026) ou
`uv run python -m apuracao.simulate --ano 2026 --passo 0.01`.
Entrada: `data/processed/pareado_{ano}.parquet`.
Saídas: `data/processed/parcial_{ano}.parquet` e
`reports/figures/parcial_{ano}.png`. Os resumos ficam também em
[SIMULACAO_PARCIAL.json](SIMULACAO_PARCIAL.json).

`snapshots(ano, passo=0.01)` fornece objetos `Snapshot` com `pct_apurado`,
`horario_corte`, `apuradas` e `faltantes` (DataFrames Polars). A tabela é lida,
filtrada por `tem_bu=True` e ordenada uma única vez por
`(recebido_em, uf, cod_municipio, zona, secao)`, preservando `ZZ`.
Uma coluna `ordem_apuracao`, de 1 a N, identifica cada posição. Os cortes usam
slices contíguos que compartilham os buffers das colunas; um teste verifica
esse compartilhamento em coluna numérica. A API não relê nem copia a tabela
inteira a cada snapshot. Os DataFrames conservam as colunas do pareamento;
modelos posteriores deverão usar votos apenas das seções já apuradas.

Cada marco gera `ceil(marco * N)` seções recebidas, com aritmética decimal
para não introduzir uma seção extra por erro de ponto flutuante. Inclui-se
100% mesmo se o passo não dividir 1; marcos que produziriam o mesmo número de
seções são omitidos. Para estes dois universos, o passo padrão produz 100
snapshots, do marco de 1% até 100%. Não há snapshot de 0%.

`pct_apurado` guarda a fração efetiva `n_apuradas / N` entre 0 e 1;
o arredondamento inteiro faz o corte ficar ligeiramente acima do marco.
`n_apuradas` e `n_faltantes` permitem reconstruí-lo exatamente. `horario_corte`
é o horário do último BU incluído, exibido em Brasília; pode haver BUs com o
mesmo segundo entre as faltantes, por causa do desempate determinístico.
BU sem horário válido ou fuso explícito interrompe a simulação; não existe
ordem sintética de reserva para 2022/2026.

As parciais são calculadas com somas acumuladas de votos, sem reprocessar todas
as seções em cada corte. `pct_13_parcial` é `100 * votos_13 / votos_validos`
acumulados; `pct_13_final` é a mesma razão para todo o universo e é conferida
com os totais oficiais independentes em `config.py` antes da publicação.
Ambas estão entre 0 e 100. `diferenca_pp` = parcial - final; não é erro absoluto.
Se um corte não tiver votos válidos, sua parcial e diferença são nulas.

`pct_apurado_N`, `pct_apurado_NE`, `pct_apurado_CO`, `pct_apurado_SE`,
`pct_apurado_S` e `pct_apurado_exterior` guardam frações entre 0 e 1:
seções recebidas **daquela região** / total de seções com BU **daquela região**.
Não representam a participação da região na parcial nacional. Se não houver
seções de uma região, a taxa é nula, não zero. As regiões derivam somente das
UFs; nenhuma fonte IBGE é usada nesta etapa.

Os testes conferem inclusão monotônica de seções, ausência de sobreposição
entre apuradas e faltantes, conservação do universo, reprodução da ordem em
entrada embaralhada, ordenação numérica das seções empatadas, cobertura regional
e igualdade da parcial com o resultado oficial em 100%. Os gráficos usam azul
neutro para a parcial do candidato 13 e cinza para o resultado final.

<!-- inicio:simulacao-parcial -->
## Parciais observadas na simulação (Prompt 4)

Resultados nos marcos configurados (passo padrão de 1% das seções com BU), arredondados para cima. Os percentuais abaixo são as frações efetivamente recebidas, e não frações de votos.

| Ano | Seções com BU | Primeiro corte com erro <1 p.p. | Abaixo de 1 p.p. até o final | Maior desvio absoluto | Corte do maior desvio |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2022 | 472028 | 62.0001% | 62.0001% | 7.3368 p.p. | 1.0002% |
| 2026 | 499205 | 1.0002% | 66.0001% | 2.3009 p.p. | 25.0002% |

O maior desvio acima é medido somente nos snapshots solicitados; não é o máximo a cada BU individual. Atingir <1 p.p. uma vez difere de permanecer nesse intervalo nos cortes seguintes. A parcial é descritiva, sem projeção das seções faltantes e sem intervalo de confiança.

<!-- fim:simulacao-parcial -->

## Modelos e prevenção de vazamento temporal

Interface: `M0().prever(snapshot)`, `M1().prever(snapshot)`, `M2().prever(snapshot)`
e `M3().prever(snapshot)` retornam `Previsao(pct_13, ic_lo, ic_hi)`, em percentual
do candidato 13 nos votos válidos, entre 0 e 100. O instante representa o corte
na ordem em que os boletins chegaram ao TSE.

O pareamento passou a incluir `bn_base = sum(comparecimento - votos_A - votos_B)
/ sum(comparecimento)`, usando exatamente o mesmo nível escolhido para as
demais taxas históricas. Os dois Parquets pareados foram regenerados; cobertura
e totais permanecem iguais. As três taxas históricas estão entre 0 e 1.

Antes de prever, M1–M3 selecionam fisicamente das faltantes **somente** `uf`,
`cod_municipio`, `aptos`, `pct_A_base`, `comparec_base` e `bn_base`. Nenhuma
outra coluna das faltantes é consultada, nem comparecimento ou brancos/nulos.
Dois testes por modelo zeram todos os resultados futuros e depois removem
inteiramente as colunas não permitidas, exigindo a mesma previsão e intervalo.
M3 é exercitado com árvores nesses testes, além do teste separado do fallback.

Para as apuradas, as taxas observadas são participação do candidato 13 nos
válidos, comparecimento/aptos e (comparecimento-válidos)/comparecimento.
O swing é taxa observada menos taxa pareada. Os pesos são, respectivamente,
válidos, aptos e comparecimento. Se o denominador de uma taxa for zero, aquela
seção não contribui para estimar seu swing. Cada taxa prevista é limitada a
[0,1]. Na faltante, válidos previstos = aptos × comparecimento previsto ×
(1 - brancos/nulos previstos); votos 13 previstos = válidos previstos ×
participação prevista. O resultado soma esses votos aos votos já recebidos.

- **M0:** parcial ingênua; `ic_lo=ic_hi=pct_13`, sem intervalo inferencial.
- **M1:** aplica a média nacional ponderada do swing a cada taxa histórica.
- **M2:** primeiro encolhe o swing médio ponderado da UF para o nacional,
  depois o municipal para o da UF: `(n * swing_observado + k * swing_pai) / (n+k)`.
  `n` é o número de seções observadas com denominador positivo para aquela taxa.
  Sem observações locais, usa o pai; `k=0` permite verificar recuperação exata
  de swings municipais em dados sintéticos.
- **M3:** três LightGBMs, um por taxa, treinados somente nas apuradas. Features:
  taxas históricas, região/UF como categorias, swings municipais/estaduais
  hierárquicos conhecidos no corte, contagens de seções observadas e indicadores
  históricos do IBGE. São 200 árvores, learning_rate=0.05, 15 folhas, profundidade
  máxima 6, mínimo 40 observações por folha, quatro threads, seed=42 e modo
  determinístico. Abaixo de 2.000 apuradas, o resultado é exatamente o do M2.

### Calibração e indicadores históricos

O padrão inicial de k é 20. A grade pré-definida `{5,20,100}` foi comparada
somente nos cortes 1%, 10%, 30% e 50% de **2022**, minimizando MAE do M2.
Foi escolhido **k=5**, congelado para os dois anos em
[CALIBRACAO_K.json](CALIBRACAO_K.json). Não houve seleção com resultados de 2026.
Esses quatro cortes de 2022 são dados de calibração; a precisão neles não é
uma validação independente da escolha de k. Os parâmetros do LightGBM não
foram ajustados pelos resultados desta aferição.

Foram usadas as edições originais de população municipal 2021 (publicação
27/08/2021) e PIB per capita 2019 (17/12/2021), nos dois anos alvo. Não se usou
o Censo 2022 nem a série atual revisada do SIDRA no backtest. Os hashes das
edições são verificados antes da leitura. ODS é lido por XML; PIB é TXT de
largura fixa nas posições do layout oficial, documentadas em
[FONTES_MODELOS.md](FONTES_MODELOS.md). Sem dependências adicionais de Excel.

O de/para oficial encontrado é de 2026 e não entra no backtest. Para anexar
os indicadores, faz-se correspondência exata de UF + nome municipal após
remover acentos/espaços/pontuação; nomes ambíguos interrompem o processamento.
Não há correspondência aproximada nem preenchimento com dados futuros.
Ficam sem indicador 13 municípios brasileiros em 2022 e 14 em 2026, além
do exterior. LightGBM recebe valores ausentes nesses casos. A lista completa
está em [INDICADORES_MODELOS.json](INDICADORES_MODELOS.json). O código IBGE
vem da planilha histórica e não é tratado como se fosse código TSE.
Os valores numéricos entram como log1p; a data de publicação é verificada
contra a data do snapshot, inclusive quando indicadores são passados à API.

### Intervalos bootstrap: implementação e limites

**Nota de versão:** a descrição abaixo registra o intervalo inicial do Prompt 5,
substituído no Prompt 6 pelos choques estruturais e pela calibração empírica
descritos na seção de avaliação. Os números do benchmark inicial permanecem
como registro histórico, não como intervalos vigentes.

M1–M3 usam 200 reamostragens, seed=42, dos resíduos das **apuradas** após o
ajuste do respectivo modelo. Os resíduos das três taxas são resumidos por
município `(uf,cod_municipio)`, com os mesmos pesos das taxas. O vetor de
erro médio municipal é a unidade de bloco; ele é centralizado na média
dos blocos. Cada município faltante recebe um bloco sorteado com reposição;
todas as suas seções recebem a mesma perturbação conjunta das três taxas.
Isso conserva dependência municipal e entre as três taxas, sem sortear seções
independentemente. Os limites são os quantis 5% e 95% dos resultados nacionais.
O LightGBM é ajustado apenas três vezes por snapshot, nunca dentro do bootstrap.

Esta aproximação usa o erro médio do bloco e pressupõe permutabilidade entre
municípios observados e faltantes. Não estima a incerteza da calibração de k,
das covariáveis ou do ajuste das árvores; os resíduos do M3 são do próprio
treino, e as features locais de treino incluem as observações disponíveis no
corte. Isso pode subestimar incerteza. A cobertura de 90% é **nominal**, não
uma garantia validada. Aferir a cobertura por progresso/região no Prompt 6.
Não se deve corrigir os intervalos usando o resultado conhecido de 2026.

Em 100% recebido, não existem faltantes: todos os modelos devolvem exatamente
o resultado apurado e intervalo degenerado. Os testes conferem esse fechamento
nos dois anos contra os totais oficiais independentes do BU.

Comandos usados na etapa inicial: `uv run python -m apuracao.features`,
`uv run python -m apuracao.models --calibrar-k` (somente 2022) e
`uv run python -m apuracao.models` (aferição de quatro cortes por ano).
`--ano 2022` repete somente aquele ano. Os tempos incluem 200 reamostragens
e o treino, mas excluem a importação inicial e a leitura/ordenação do arquivo.

<!-- inicio:modelos-benchmark -->
## Aferição rápida dos modelos (Prompt 5)

Percentuais do candidato 13 nos votos válidos, na ordem em que os boletins chegaram ao TSE. Somente cortes de 1%, 10%, 30% e 50%; não é a avaliação completa.

| Ano | Corte | Modelo | Previsto (%) | Erro (p.p.) | Intervalo nominal 90% | Inclui o final? | Tempo (s) |
| --- | ---: | --- | ---: | ---: | --- | --- | ---: |
| 2022 | 10% | M0 | 47.9884 | -2.9140 | sem IC | — | 0.0001 |
| 2022 | 10% | M1 | 50.3379 | -0.5645 | [49.4916; 51.1051] | sim | 3.6287 |
| 2022 | 10% | M2 | 51.2953 | +0.3929 | [50.8985; 51.5886] | sim | 4.2607 |
| 2022 | 10% | M3 | 51.0140 | +0.1116 | [50.7875; 51.2046] | sim | 11.0971 |
| 2022 | 30% | M0 | 48.9461 | -1.9563 | sem IC | — | 0.0002 |
| 2022 | 30% | M1 | 50.2148 | -0.6876 | [49.5557; 50.8149] | não | 3.0052 |
| 2022 | 30% | M2 | 51.3341 | +0.4317 | [51.1673; 51.4935] | não | 3.6562 |
| 2022 | 30% | M3 | 51.0971 | +0.1947 | [50.9506; 51.2413] | não | 13.3834 |

| Ano | Corte | M0 (s) | M1 (s) | M2 (s) | M3 (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2022 | 1% | 0.0000 | 3.9178 | 4.4466 | 9.6756 |
| 2022 | 10% | 0.0001 | 3.6287 | 4.2607 | 11.0971 |
| 2022 | 30% | 0.0002 | 3.0052 | 3.6562 | 13.3834 |
| 2022 | 50% | 0.0003 | 2.3162 | 3.0243 | 15.5424 |
| 2026 | 1% | 0.0000 | 4.5267 | 5.2567 | 12.4809 |
| 2026 | 10% | 0.0001 | 7.4127 | 5.0529 | 12.4967 |
| 2026 | 30% | 0.0002 | 3.2761 | 3.9122 | 14.0098 |
| 2026 | 50% | 0.0003 | 2.3308 | 3.1697 | 15.4570 |

Tempos pontuais desta máquina, não um teste de latência isolado. Excluem importação e leitura/ordenação dos Parquets; incluem preparação de características, treino e 200 reamostragens para M1–M3. M0 não faz bootstrap.

A meta pontual <1 p.p. a 30% foi atingida nesta aferição de 2022 por M1–M3. Os mesmos cortes de 2022 participaram da seleção de k; logo não são teste independente da calibração. Os intervalos de M1, M2 e M3 em 30% de 2022 não contiveram o final. A cobertura nominal de 90% não está demonstrada; avaliar a cobertura no Prompt 6, sem ajustar intervalos para encaixar o resultado de 2026.

<!-- fim:modelos-benchmark -->

## Avaliação e intervalos estruturais (Prompt 6)

**2022 é desenvolvimento/calibração. 2026 é teste fora da amostra.** O valor
de k=5 continua fixo. As previsões pontuais dos modelos não foram alteradas.
O ajuste é no mecanismo de incerteza e em sua escala empírica.

O erro original foi reproduzido em teste sintético: milhares de municípios
faltantes de uma mesma UF recebiam resíduos independentes e o intervalo ficava
com cerca de 0,54 p.p. de largura, apesar de swings observados por UF distintos.
A regressão agora exige que o choque comum não desapareça pela média entre
municípios; ela falhou antes da correção e passou depois.

Em cada reamostragem de M1–M3 há três componentes aplicados às faltantes:

1. O resíduo médio municipal, em bloco, preservando o vetor das três taxas.
2. Um choque comum para cada UF faltante, sorteado dos swings médios das UFs
   observadas menos o swing nacional ponderado. Todas as seções da mesma UF
   compartilham o choque; ele não é centralizado dentro de cada município.
3. Um choque nacional comum a todas as faltantes. Seu desvio-padrão é a dispersão
   entre swings de UF dividida pela raiz do número efetivo de UFs observadas
   (obtido pelas contagens de seções, separadamente para cada taxa).

Se só houver uma UF observada, usa-se a dispersão municipal para o erro da
média nacional. O mecanismo não conhece os swings verdadeiros das faltantes.
As taxas são limitadas a [0,1], os 200 resultados nacionais são agregados, e
usa-se uma envoltória bilateral da projeção pontual, com raio igual à maior
distância entre ela e os quantis de 5%/95%. Assim, um deslocamento comum em
um só sentido não elimina artificialmente a incerteza do outro lado. Os
limites finais são limitados a [0,100].
O LightGBM não é retreinado dentro das reamostragens.

### Calibração da escala e congelamento

São usados exclusivamente os 99 cortes de 2022. As faixas foram fixadas antes
de avaliar 2026: marcos 1–10%, 11–20%, ..., 91–99%. Para cada modelo e faixa,
o escore é `abs(real - previsto) / semilargura_estrutural_do_lado_do_erro`.
O fator é o escore de ordem `ceil(0.9 * n)`, a menor escala que cobre pelo
menos 90% dos cortes daquela faixa de desenvolvimento. Os dois lados do
intervalo são multiplicados pelo mesmo fator e limitados a [0,100]. O fator
pode ser menor que 1 quando o intervalo estrutural já era conservador.

Os fatores, tamanhos das faixas, ordem do quantil, cobertura antes/depois,
data de congelamento e assinatura do experimento ficam em
`docs/CALIBRACAO_IC.json`. O arquivo é salvo **antes** da avaliação de 2026,
e seu SHA-256 é conferido ao final para impedir reajuste durante o teste.
Nenhum erro de 2026 entra na calibração. A API normal `prever` aplica esse
arquivo quando ele existe; `calibrar_ic=False` retorna somente o intervalo
estrutural para gerar os dados de desenvolvimento sem aplicação circular.

Esta é calibração empírica inspirada em escores conformais, não uma garantia
conformal: snapshots sucessivos são dependentes e 2022 também foi usado para
escolher k. A referência conceitual é
[Angelopoulos e Bates, A Gentle Introduction to Conformal Prediction](https://arxiv.org/abs/2107.07511).
O teste de 2026 mede a transferência real da escala, inclusive se a cobertura
ficar abaixo ou acima de 90%. Não haverá novo ajuste com base nesse resultado.

### Execução e relatório

Comando: `uv run python -m apuracao.evaluate --workers 2 --n-jobs 2`.
Na execução final usaram-se quatro processos com uma thread LightGBM cada
(`--workers 4 --n-jobs 1`). Os choques são somados por município antes da
expansão para seções, uma otimização algébrica conferida contra a formulação
anterior com tolerância de 1e-10 p.p. Não há mudança das reamostragens.
Cada processo carrega o pareamento uma vez e usa slices dos mesmos buffers.
Tarefas são persistidas individualmente em `data/processed/avaliacao_cache/`,
com assinatura do código, configuração e Parquets. Uma retomada reutiliza
somente tarefas com a mesma assinatura. O progresso fica em
`data/processed/avaliacao_progresso.json`. São 792 linhas finais: dois anos,
99 snapshots e quatro modelos. Não se inclui 100%, pois o intervalo nesse
corte é degenerado por definição e inflaria a cobertura.

Saída: `data/processed/avaliacao.parquet`, com `ano`, `modelo`, `pct_apurado`,
`horario_corte`, `previsto`, `ic_lo`, `ic_hi`, `real`, `erro_pp` e `cobriu`.
Campos adicionais de auditoria: marco nominal, limites estruturais antes do
fator, fator aplicado e segundos de previsão. Os instantes têm fuso explícito;
converter para Brasília na exibição. `docs/RESULTADOS.md` resume os dois anos,
os erros em 10/30/50%, a cobertura dos 99 cortes e a estabilidade do líder.

O líder estável é o candidato projetado em 99%; localiza-se retrospectivamente
a última mudança anterior. O relatório confere esse líder com o vencedor real.
Isso não equivale a o intervalo já excluir 50% no primeiro corte estável.
M0 continua sem intervalo inferencial: seu `cobriu` no Parquet corresponde
apenas à igualdade com o intervalo degenerado, sem cobertura nominal atribuída.

O código dos cálculos foi preservado no commit `f720fc2`. Uma correção posterior
de integração da API faz o M3 usar também o fator do M2 quando cai para M2
abaixo de 2.000 apuradas. Ela não altera os cálculos desta avaliação: todos
os cortes de 1% a 99% têm mais de 2.000 apuradas, e os trabalhadores produzem
intervalos brutos com `calibrar_ic=False`. O teste específico falhou com os
fatores novos antes dessa correção e passou depois. Os fatores congelados
para 2026 permanecem byte a byte iguais.

## Apresentação e diagnóstico posterior (Prompt 7)

As figuras principais de 2022 e 2026 têm 1080×1350 pixels, usam nomes neutros,
cinza/azul, linhas M0 e M3, resultado final e referência de 50%. A sombra marca
os intervalos de cortes em que a parcial indicava o outro líder; empates não
são classificados como líder errado. A estabilidade do líder é verificada nos
99 cortes avaliados, não a cada BU individual.

A faixa exibida é a estrutural bruta, lida diretamente de `ic_lo_bruto` e
`ic_hi_bruto` da avaliação congelada. Cada gráfico declara **faixa conservadora,
sem cobertura nominal validada** e que essa escolha foi feita **APÓS ver 2026**.
Não se substituíram os limites calibrados no Parquet. A opção de apresentação
é posterior ao teste, portanto não pode ser apresentada como escolha validada
fora da amostra. A comparação de erros não usa intervalos.

Comandos: `uv run python -m apuracao.bias` e
`uv run python -m apuracao.plots`. O primeiro reconstrói apenas o corte de 30%
de cada ano, sem bootstrap nem seleção de parâmetros, e confere a projeção
com a linha congelada da avaliação. Só então acessa as respostas das faltantes
para substituições oraculares. Shapley exato atribui as interações entre taxas
sem escolher uma ordem de correção; as três taxas são corrigidas no Brasil e
ZZ constitui um bloco separado. As quatro contribuições somam o erro total.
O componente predominante é a participação/swing prevista; a causa do viés
das árvores não foi isolada e não se ajustou o modelo. Resultados completos em
[RESULTADOS.md](RESULTADOS.md) e [DIAGNOSTICO_VIES.json](DIAGNOSTICO_VIES.json).

O mapa é exclusivamente descritivo. Soma os votos de cada município em cada
ano e calcula `100 * (votos_13_2026 / validos_2026 - votos_13_2022 / validos_2022)`.
Usa apenas pares de municípios com dados nas duas eleições, sem imputar o
resultado de município novo. A correspondência oficial TSE–IBGE de 2026,
já inspecionada (`CD_MUNICIPIO_TSE`, `CD_MUNICIPIO_IBGE`, `SG_UF`), é usada
somente no mapa; não é introduzida no backtest. O exterior não tem geometria
municipal brasileira, fica fora do mapa e continua nos resultados nacionais.

Fonte da correspondência: [TSE](https://dadosabertos.tse.jus.br/dataset/codigos-oficiais-de-uf-e-municipios-segundo-o-tse-e-o-ibge).
Geometrias: [geobr/IBGE](https://github.com/ipea/geobr), `read_municipality(year=2022)`.
Leitura pela saída DuckDB e conversão WKB contorna o `fetchone` legado do
conversor GeoPandas da versão instalada. Não se modificou a biblioteca. O cache
municipal fica em `data/raw/geobr/municipios_2022.parquet`; o CRS original é
EPSG:4674 e o mapa usa EPSG:5880. São 5.570 geometrias com comparação; o
relatório de cobertura e a escala simétrica de ±16 p.p. estão em
[COBERTURA_MAPA.json](COBERTURA_MAPA.json). A paleta azul–cinza–violeta tem
centro em zero e não usa cores partidárias carregadas.

O notebook `notebooks/02_resultados.ipynb` foi executado com Python 3.12.
Seus blocos de código apenas importam e chamam funções; toda a lógica está
em `src/apuracao/`. Figuras, rótulos e dimensões foram revisados visualmente.
[FIGURAS_AUDITORIA.json](FIGURAS_AUDITORIA.json) registra a decisão posterior
e os hashes dos três arquivos protegidos antes/depois da geração.
