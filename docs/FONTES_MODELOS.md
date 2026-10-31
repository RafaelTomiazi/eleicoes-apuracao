# Fontes históricas para modelos com corte em 30/10/2022

Verificação em 31/10/2026. Recomenda-se usar os arquivos históricos abaixo, preservados no diretório de cada edição, em vez de consultar retroativamente a série SIDRA atual. Foram baixados com cache em `data/raw/ibge_historico/` sem alterar código.

## Indicadores com publicação anterior ao corte

| Indicador | Referência | Publicação original comprovada | Arquivo recomendado |
| --- | --- | --- | --- |
| População municipal estimada | 01/07/2021 | 27/08/2021 | `estimativa_dou_2021.ods` ou `.xls` |
| PIB municipal e PIB per capita a preços correntes | 2019 | 17/12/2021 | `base_de_dados_2010_2019_txt.zip`, filtrar ano 2019 |

A [divulgação oficial das estimativas de população 2021](https://agenciadenoticias.ibge.gov.br/agencia-sala-de-imprensa/2013-agencia-de-noticias/releases/31461-ibge-divulga-estimativa-da-populacao-dos-municipios-para-2021) registra publicação em 27/08/2021 e atualização em 08/09/2021, ambas anteriores ao corte. A [edição oficial do PIB municipal 2019](https://www.ibge.gov.br/estatisticas/economicas/contas-nacionais/9088-produto-interno-bruto-dos-municipios.html?edicao=32575) identifica a referência 2019 e divulgação em 17/12/2021.

**Não usar PIB 2020 nesse corte**: a [notícia oficial de lançamento](https://agenciadenoticias.ibge.gov.br/agencia-noticias/2012-agencia-de-noticias/noticias/35890-pandemia-derruba-o-pib-dos-grandes-centros-urbanos-em-2020) foi publicada em 16/12/2022. O fato de a referência ser 2020 não significa que o valor já era conhecido em outubro de 2022. Os indicadores do Censo 2022 publicados posteriormente também não são covariáveis elegíveis para previsão histórica nessa data.

## População: versão histórica disponível

O [diretório oficial Estimativas 2021](https://ftp.ibge.gov.br/Estimativas_de_Populacao/Estimativas_2021/) distingue claramente os arquivos:

- `estimativa_dou_2021.ods`, `.xls`, `.pdf`: listados com data 27/08/2021 09:00.
- `POP2021_20240624.ods`, `.xls`, `.pdf`: listados com data 24/06/2024. Estes últimos são posteriores ao corte e não devem substituir silenciosamente a edição original.

Downloads verificados e armazenados:

| Arquivo e URL | Bytes | Last-Modified HTTP | SHA-256 |
| --- | ---: | --- | --- |
| [estimativa_dou_2021.ods](https://ftp.ibge.gov.br/Estimativas_de_Populacao/Estimativas_2021/estimativa_dou_2021.ods) | 193832 | Fri, 27 Aug 2021 12:00:04 GMT | `57746ed3f495f1f3111ed4ed33ee59d6e9ddd4f7023c25434fc79cd1e5b6a8bb` |
| [estimativa_dou_2021.xls](https://ftp.ibge.gov.br/Estimativas_de_Populacao/Estimativas_2021/estimativa_dou_2021.xls) | 759808 | Fri, 27 Aug 2021 12:00:04 GMT | `6800abbd5b97fa8fb978bfaa5afa34f800b70ef0c9ac01ea3c3b95325d771736` |

O ODS pode ser lido sem dependência de Excel: é ZIP com `content.xml`; usar `zipfile` e `xml.etree.ElementTree`, respeitando as repetições de células/linhas do formato ODF. A aba `Municípios` contém, após o título, as colunas reais `UF`, `COD. UF`, `COD. MUNIC`, `NOME DO MUNICÍPIO`, `POPULAÇÃO ESTIMADA`. O código municipal IBGE é a concatenação de `COD. UF` (2 dígitos) com `COD. MUNIC` (5 dígitos, incluindo zeros à esquerda). A população exibida contém separadores de milhar, por exemplo `22.516` para Alta Floresta D'Oeste (1100015). Tratar notas de rodapé como notas, não como dados municipais.

## PIB: edição 2019 preservada

O [diretório oficial da base PIB 2019](https://ftp.ibge.gov.br/Pib_Municipios/2019/base/) lista a base 2010–2019 com data 17/12/2021 10:00. O [ZIP TXT original](https://ftp.ibge.gov.br/Pib_Municipios/2019/base/base_de_dados_2010_2019_txt.zip) foi baixado: 5894199 bytes, `Last-Modified: Fri, 17 Dec 2021 13:00:03 GMT`, SHA-256 `11e50dfb372acfa030ebfa78445a299a371838710925bcdd5bbf4ae931462da2`.

O ZIP contém `layout_da_base_de_dados_2010_2019_em_formato_txt.pdf` e TXT sem cabeçalho, em largura fixa. Decodificação cp1252 verificada; 55.685 linhas no conjunto 2010–2019. O layout oficial determina:

| Campo | Posição inicial oficial, base 1 | Tamanho | Slice Python, base 0 | Unidade |
| --- | ---: | ---: | --- | --- |
| Ano | 1 | 4 | `[0:4]` | ano |
| Código do Município | 47 | 7 | `[46:53]` | código IBGE |
| Produto Interno Bruto, a preços correntes | 934 | 18 | `[933:951]` | R$ 1.000 |
| Produto Interno Bruto per capita, a preços correntes | 953 | 18 | `[952:970]` | R$ 1,00 |

O TXT usa ponto decimal. Filtrar 2019 após a leitura, sem dividir pelo espaço entre palavras. Usar diretamente o PIB per capita oficial, cujo denominador segue as estimativas de população da edição, em vez de recalculá-lo com população 2021. O próprio layout avisa que os dados de 2019 estavam sujeitos à revisão na próxima publicação; isso reforça a necessidade de manter essa edição.

## Por que a consulta SIDRA atual não é a edição histórica

Endpoints brutos testados, úteis apenas para comparação ou aquisição contemporânea:

- https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/2021 — população estimada 2021, unidade pessoas. Retornou **5.571 registros**, incluindo Boa Esperança do Norte (5101837) com `V="..."`. O registro adicional evidencia que o universo de apresentação atual não coincide automaticamente com o arquivo municipal original de 2021.
- https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/2019 — PIB total 2019 em mil reais, 5.570 registros. A tabela atual pode incorporar revisões; o parâmetro `p/2019` fixa referência e não versão de publicação.

Para o modelo histórico, preferir os arquivos originais baixados. As evidências de diretório, nomes de edição e Last-Modified anteriores ao corte sustentam o uso dessas edições; não constituem prova criptográfica de imutabilidade desde 2021. Os hashes acima fixam os bytes efetivamente obtidos agora. Identificar no relatório “edição histórica 2021, recuperada em 2026”, evitando afirmar uma captura arquivada feita em 2021.

## Correspondência oficial TSE–IBGE

O [conjunto oficial de códigos TSE e IBGE](https://dadosabertos.tse.jus.br/dataset/codigos-oficiais-de-uf-e-municipios-segundo-o-tse-e-o-ibge) oferece o [ZIP municipio_tse_ibge](https://cdn.tse.jus.br/estatistica/sead/odsele/municipio_tse_ibge/municipio_tse_ibge.zip), armazenado em `data/raw/ibge_historico/municipio_tse_ibge.zip`. O CSV usa latin-1 e `;`, com campos reais `CD_MUNICIPIO_TSE`, `CD_MUNICIPIO_IBGE`, `SG_UF`, nomes municipais e códigos de UF.

**Limitação temporal:** o catálogo foi criado em 24/06/2025 e o CSV obtido informa geração 25/10/2026 09:00:09. Portanto, é uma correspondência oficial atual, não uma tabela histórica comprovadamente disponível em 2022. Pode apoiar reconciliação de identificadores estáveis mediante validação de nomes/UF e relatório de exceções, mas não se deve rotulá-la como correspondência vintage 2022. Não usar agregações ou imputações que incorporem municípios inexistentes na malha histórica.

Também foi validado o [JSON oficial de municípios da eleição 2026](https://resultados.tse.jus.br/oficial/ele2026/6257/config/mun-e006257-cm.json): `abr[].mu[].cd` identifica TSE e `cdi` identifica IBGE. Ele possui a mesma limitação temporal. A URL equivalente de 2022 (`ele2022/544/config/mun-e000544-cm.json`) retornou HTTP 404 na consulta atual; não foi encontrada uma versão histórica oficial acessível nesta pesquisa.
