# teste_agent.py
from ai_agent import responder_chat, pergunta_pede_grafico

perguntas = [
    "Quantos deals temos no CRM?",
    "Qual o valor total do pipeline?",
    "Me mostra um gráfico dos deals por estágio",
]

for p in perguntas:
    print(f"\n>>> {p}")
    print(f"    pede gráfico: {pergunta_pede_grafico(p)}")
    resposta = responder_chat(p, historico=[])
    print(f"    resposta: {resposta[:200]}...")