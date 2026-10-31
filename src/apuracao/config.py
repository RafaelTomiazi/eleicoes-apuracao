"""Configurações confirmadas para comparação entre eleições."""

CANDIDATES: dict[int, dict[str, int]] = {
    2018: {"A": 13, "B": 17},
    2022: {"A": 13, "B": 22},
    2026: {"A": 13, "B": 22},
}

# Confirmado pelo usuário: 13 é o único número presente nos três anos;
# num 2º turno %B = 100 - %A, então a escolha só define o sinal do swing,
# não altera projeções nem erros (em modelos equivalentes ao trocar os lados).
# Os totais oficiais serão lidos de fontes independentes do BU, sem números de memória.

# Fontes: https://dadosabertos.tse.jus.br/dataset/resultados-{ano}
# ZIPs votacao_candidato_munzona e detalhe_votacao_munzona; somente _BR.csv,
# CD_CARGO=1, NR_TURNO=2, SG_UE=BR; valores conferidos em 31/10/2026.
OFFICIAL_TOTALS: dict[int, dict[str, int]] = {
    2018: {"aptos": 147306294, "votos_A": 47040906, "votos_B": 57797847, "votos_validos": 104838753},
    2022: {"aptos": 156454011, "votos_A": 60345999, "votos_B": 58206354, "votos_validos": 118552353},
    2026: {"aptos": 158745502, "votos_A": 64256232, "votos_B": 59826041, "votos_validos": 124082273},
}

# Inferência documentada: igualdade com Hora TSE no detalhe por seção e normas
# https://www.tse.jus.br/legislacao/compilada/res/2021/resolucao-no-23-669-de-14-de-dezembro-de-2021 (art.254)
# https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-751-de-26-de-fevereiro-de-2026 (art.282)
RECEIVED_TIMEZONE: dict[int, str | None] = {2018: None, 2022: "America/Sao_Paulo", 2026: "America/Sao_Paulo"}
