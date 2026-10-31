# Fontes IBGE verificadas

Consulta técnica realizada em 31/10/2026. URLs abaixo foram chamadas diretamente; a quantidade de registros exclui a primeira linha de metadados do JSON SIDRA. São fontes primárias do IBGE.

## Consultas municipais utilizáveis

| Indicador | Tabela / variável | Período mais recente observado | Registros municipais | URL JSON verificada |
| --- | --- | --- | --- | --- |
| População residente estimada, pessoas | 6579 / 9324 | 2026 | 5.571 | https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/2026 |
| População residente do Censo, pessoas | 4714 / 93 | 2022 | 5.570 | https://apisidra.ibge.gov.br/values/t/4714/n6/all/v/93/p/2022 |
| PIB a preços correntes, **mil reais** | 5938 / 37 | 2023 | 5.570 | https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/2023 |
| Rendimento nominal médio mensal domiciliar per capita, reais | 10295 / 13431 | 2022 | 5.570 | https://apisidra.ibge.gov.br/values/t/10295/n6/all/v/13431/p/2022 |
| Taxa de alfabetização de pessoas de 15 anos ou mais, % | 9543 / 2513 | 2022 | 5.570 | https://apisidra.ibge.gov.br/values/t/9543/n6/all/v/2513/p/2022 |

A renda abrange moradores em domicílios particulares permanentes ocupados, excluídos pensionistas, empregados domésticos e parentes destes; o nome completo está em `D2N`. As classificações omitidas nesta consulta retornam os totais de sexo, grupo de idade e cor ou raça. A divulgação é de resultados preliminares da amostra do Censo, conforme a [página oficial de Trabalho e rendimento](https://www.ibge.gov.br/estatisticas/Sociais/populacao/22827-censo-demografico-2022.html?edicao=44663). PIB per capita e rendimento domiciliar per capita medem conceitos distintos.

Como medida de educação, a alfabetização é um indicador específico; não deve ser rotulada como anos de estudo ou escolaridade média. Pode-se derivar analfabetismo como `100 - taxa_alfabetizacao`. Alternativa com contagens verificadas: https://apisidra.ibge.gov.br/values/t/9542/n6/3550308/v/950/p/2022/c59/all retorna total (categoria 93024), alfabetizadas (1023) e não alfabetizadas (1024). A dimensão de alfabetização é `c59`.

## PIB per capita: usar a base oficial da pesquisa

A consulta `v/all` da tabela 5938 **não retornou variável de PIB per capita**. A variável 543 é impostos líquidos de subsídios, não PIB per capita. A tabela 6784 é de Contas Nacionais, não uma alternativa municipal. A [página oficial do PIB dos Municípios](https://www.ibge.gov.br/estatisticas/economicas/contas-nacionais/9088-produto-interno-bruto-dos-municipios.html?c=3165602&t=pib-por-municipio) oferece a base 2010–2023 e os conceitos da pesquisa.

Downloads oficiais verificados:

- [Base 2010–2023 em TXT compactado](https://ftp.ibge.gov.br/Pib_Municipios/2022_2023/base/base_de_dados_2010_2023_txt.zip): HTTP 200, 7.750.036 bytes. Contém o PDF de layout e TXT de largura fixa, sem cabeçalho; a decodificação cp1252 funciona. Foram observadas 77.965 linhas e anos 2010 a 2023. Usar as posições do PDF de layout, sem separar por espaços, pois nomes possuem espaços.
- [Base 2010–2023 em XLSX compactado](https://ftp.ibge.gov.br/Pib_Municipios/2022_2023/base/base_de_dados_2010_2023_xlsx.zip): HTTP 200, 20.696.280 bytes. Preferível para inspecionar os nomes originais de colunas antes da implementação.

O TXT inclui PIB total e PIB per capita: a última linha, Brasília em 2023, contém PIB total de 365669107.906 mil reais e PIB per capita de 129790.44 reais. Não dividir o PIB de 2023 pela população de outro ano e apresentar o resultado como o PIB per capita oficial.

## Metadados, períodos e validação da resposta

A primeira linha JSON do SIDRA é um dicionário de descrições (`D1C`, `D1N`, `D2C`, etc.), não uma observação. Nas consultas da tabela acima, `D1C` identifica o município IBGE, `D2C` a variável e `D3C` o ano. `V` é string numérica com ponto decimal; `MN` é a unidade. Ler esses nomes da primeira linha: a ordem das dimensões pode mudar quando classificações são incluídas na URL. Manter o código municipal como texto de sete dígitos e nunca usá-lo como código TSE sem correspondência oficial.

Para descobrir períodos sem baixar todos os municípios, consultar um município com `p/all`:

- [Períodos da população estimada](https://apisidra.ibge.gov.br/values/t/6579/n6/3550308/v/9324/p/all): 2001–2006, 2008–2009, 2011–2021, 2024–2026. A ausência de 2007, 2010, 2022 e 2023 não deve ser preenchida silenciosamente com estimativas inventadas.
- [Períodos do PIB municipal](https://apisidra.ibge.gov.br/values/t/5938/n6/3550308/v/37/p/all): 2002 a 2023.
- Para explorar variáveis: [renda `v/all`](https://apisidra.ibge.gov.br/values/t/10295/n6/3550308/v/all/p/last), [alfabetização `v/all`](https://apisidra.ibge.gov.br/values/t/9543/n6/3550308/v/all/p/last) e [população censitária `v/all`](https://apisidra.ibge.gov.br/values/t/4714/n6/3550308/v/all/p/last). `p/last` é somente descoberta; fixar o ano no manifesto reprodutível.

Os endpoints documentais `https://servicodados.ibge.gov.br/api/v3/agregados/{tabela}/metadados` e `/periodos` retornaram HTML `Request Rejected` com **HTTP 200**, neste ambiente. O mesmo ocorreu com `https://servicodados.ibge.gov.br/api/v1/pesquisas/indicadores/29171/resultados/all`. Portanto, não declarar esses downloads bem-sucedidos apenas pelo status HTTP; validar tipo de conteúdo, JSON e esquema antes de gravar o cache. O SIDRA direto funcionou nas URLs acima. Os valores especiais como `...` devem ser conservados no bruto e convertidos para nulo no tratamento, não para zero.

## Uso temporal e cobertura

Para análises retrospectivas de eleição, distinguir ano de referência, data de publicação e data de extração. Um dado do Censo de referência 2022 divulgado em 2025 não era uma informação disponível na eleição de 2022. Selecionar a última divulgação efetivamente disponível antes do corte eleitoral quando o objetivo for previsão; usar divulgações posteriores apenas em análise descritiva, identificando essa escolha. Preservar URL, ano, data de coleta, hash e versão do arquivo bruto em cache idempotente; tabelas podem ser revisadas.

As contagens municipais diferem entre anos e pesquisas (5.571 nas estimativas de 2024/2026 versus 5.570 no Censo 2022 e PIB 2023). Fazer junção com relatório de cobertura e faltantes; não exigir a mesma malha territorial sem verificar criação, alteração ou extinção de municípios. População residente também não é eleitorado.
