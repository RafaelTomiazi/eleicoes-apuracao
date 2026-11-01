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
