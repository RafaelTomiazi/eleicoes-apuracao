# Resultados da avaliação

Ordem em que os boletins chegaram ao TSE. Cortes de 1% a 99% das seções com BU; empates pela chave da seção. Percentuais de progresso nas tabelas são marcos arredondados.

**2022 = desenvolvimento/calibração (k e fator do IC escolhidos aqui).**

**2026 = teste fora da amostra.** Os fatores dos intervalos foram congelados antes de iniciar a execução de 2026; não houve reajuste pelo desempenho no teste.

Tempo total desta execução: **52.31 minutos** (3138.70 s); 4 processos, 1 thread(s) LightGBM por processo e 200 reamostragens por intervalo.

**Resultado central do M3 em 2026:** cobertura de **6.06% (6/99)**; líder pontual estável desde **1%**.

**A meta de cobertura não foi atingida fora da amostra.** Os intervalos calibrados não devem ser apresentados como tendo cobertura de 90% validada. A boa precisão pontual não corrige essa falha. Os fatores foram mantidos: não se ajustou 2026 para melhorar o resultado.

Código numérico do experimento: commit `f720fc28c7af61c3ca541e8419c185bad7c03627`. Revisões posteriores de integração/apresentação não mudaram os cálculos brutos.

## 2022

| Modelo | Erro em 10% (p.p.) | Erro em 30% (p.p.) | Erro em 50% (p.p.) | Cobertura IC | Líder estável desde | Líder em 99% | Confere final? |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| M0 | -2.9140 | -1.9563 | -1.2072 | sem IC | 68% | candidato 13 | sim |
| M1 | -0.5645 | -0.6876 | -0.4627 | 90.91% (90/99) | 1% | candidato 13 | sim |
| M2 | +0.3929 | +0.4317 | +0.3483 | 90.91% (90/99) | 1% | candidato 13 | sim |
| M3 | +0.1116 | +0.1947 | +0.1410 | 90.91% (90/99) | 1% | candidato 13 | sim |

| Modelo | Largura média do IC (p.p.) | Cobertura estrutural antes do fator |
| --- | ---: | ---: |
| M1 | 1.0178 | 100.00% |
| M2 | 0.6860 | 100.00% |
| M3 | 0.3047 | 100.00% |

## 2026

| Modelo | Erro em 10% (p.p.) | Erro em 30% (p.p.) | Erro em 50% (p.p.) | Cobertura IC | Líder estável desde | Líder em 99% | Confere final? |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| M0 | -1.3041 | -2.2354 | -1.6682 | sem IC | 48% | candidato 13 | sim |
| M1 | +0.2909 | -0.3403 | -0.4170 | 19.19% (19/99) | 1% | candidato 13 | sim |
| M2 | +0.2851 | +0.2955 | +0.1816 | 7.07% (7/99) | 1% | candidato 13 | sim |
| M3 | +0.0854 | +0.2261 | +0.0801 | 6.06% (6/99) | 1% | candidato 13 | sim |

| Modelo | Largura média do IC (p.p.) | Cobertura estrutural antes do fator |
| --- | ---: | ---: |
| M1 | 0.3850 | 100.00% |
| M2 | 0.2521 | 100.00% |
| M3 | 0.1114 | 100.00% |

## Interpretação e limites

A estabilidade do vencedor é uma constatação retrospectiva da projeção pontual nos cortes até 99%; não significa que o intervalo já excluía 50% naquele instante.

A cobertura é a proporção dos 99 cortes cujo intervalo contém o único resultado nacional final. Os cortes são dependentes; não são 99 eleições independentes. A calibração por faixas é empírica, inspirada em escores conformais, sem garantia conformal de 90% no ano seguinte. A cobertura em 2022 é ajustada por construção.

Os intervalos estruturais brutos e os intervalos após o fator estão comparados nas tabelas. Cobertura bruta de 100% nesta única eleição também não demonstra calibração de 90%: pode indicar conservadorismo. A contração de escala aprendida em 2022 não se transferiu adequadamente; não se escolheu outra escala após observar o teste.

M0 é uma parcial sem intervalo inferencial: o Parquet mantém os limites degenerados e o campo cobriu, mas não se atribui cobertura nominal de 90% a esse modelo.

Fontes de totais: arquivos oficiais independentes do BU registrados em config.py. Indicadores: edições históricas publicadas até 2021, documentadas em FONTES_MODELOS.md. Calibração fixa: [CALIBRACAO_IC.json](CALIBRACAO_IC.json).

<!-- inicio:licoes-vies -->
## O que a falha de cobertura ensinou

A calibração contraiu a faixa estrutural de 2022. O valor próximo de 0,22 não representa todos os modelos: os fatores efetivamente salvos são:

| Modelo | Menor fator | Maior fator | Largura média após/antes, em 2022 |
| --- | ---: | ---: | ---: |
| M1 | 0.0549 | 0.2386 | 0.1982 |
| M2 | 0.1092 | 0.1524 | 0.1354 |
| M3 | 0.0308 | 0.0756 | 0.0602 |

No corte de 30%, o desvio-padrão dos swings médios observados por UF foi 5.2057 p.p. em 2022 e 1.9712 p.p. em 2026 (UFs com válidos já recebidos; dispersão não ponderada entre médias estaduais ponderadas por válidos). A largura bruta média do M3 caiu de 5.0593 para 1.8387 p.p. A faixa já nasceu mais estreita em 2026 e recebeu a mesma contração de escala. O erro pontual não diminuiu na mesma proporção.

Uma eleição de calibração é **uma realização do processo eleitoral**: os 99 cortes são a mesma noite vista repetidamente e são autocorrelacionados. Não equivalem a 99 eleições independentes. Isso não permite estimar literalmente um tamanho amostral efetivo igual a 1, mas há apenas uma eleição de calibração para julgar a transferência entre eleições.

**Decisão de apresentação feita APÓS ver 2026:** os gráficos usam a FAIXA ESTRUTURAL BRUTA, rotulada **faixa conservadora, sem cobertura nominal validada**. Ela cobriu 100% dos cortes dos dois anos observados. Essa escolha posterior não é uma validação fora da amostra da escolha de faixa, não retoca o teste e não demonstra probabilidade de cobertura de 90% em outra eleição. A avaliação, os fatores e os limites calibrados originais permanecem intactos.

## Diagnóstico de viés do M3 em 30%

Os dados futuros abaixo são usados **apenas para diagnóstico retrospectivo**. Primeiro reproduz-se a previsão congelada; depois substituem-se, por valores reais, as taxas das faltantes. Os três componentes de taxas são domésticos; o exterior é corrigido como quarto bloco, evitando dupla contagem. O Shapley exato das 24 ordens de substituição reparte as interações da razão nacional e soma ao erro total. Sinal positivo contribui para superestimar o candidato 13; negativo compensa o erro.

| Componente | 2022 (p.p.) | 2026 (p.p.) |
| --- | ---: | ---: |
| Comparecimento | -0.000677 | -0.014173 |
| Brancos/nulos | +0.001665 | +0.000283 |
| Swing / participação prevista | +0.194106 | +0.239887 |
| Exterior (ZZ) | -0.000434 | +0.000152 |
| **Erro total** | **+0.194660** | **+0.226148** |

A participação prevista (base + swing) é a contribuição dominante nos dois anos. Em 2026, o comparecimento compensa parte da superestimação; por isso a contribuição do swing é maior que o erro líquido. Brancos/nulos e ZZ têm efeitos pequenos. Isso identifica o componente da projeção que carrega o erro, mas não demonstra a causa do viés no LightGBM. Não se ajustou o swing, k, as árvores nem os intervalos.

| Ano | Modelo | Erro médio nos 99 cortes (p.p.) | Cortes com erro positivo |
| --- | --- | ---: | ---: |
| 2022 | M2 | +0.3012 | 100.00% |
| 2022 | M3 | +0.1138 | 93.94% |
| 2026 | M2 | +0.1738 | 96.97% |
| 2026 | M3 | +0.1318 | 92.93% |

O padrão é compatível com viés de superestimação nestes dados. A faixa +0,1 a +0,2 p.p. descreve o erro médio do M3; M2 em 2022 fica próximo de +0,3 p.p. Duas eleições não estabelecem uma magnitude universal. Detalhes e taxas agregadas das faltantes estão em [DIAGNOSTICO_VIES.json](DIAGNOSTICO_VIES.json).

<!-- fim:licoes-vies -->
