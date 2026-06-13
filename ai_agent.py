"""
ai_agent.py — Agente conversacional com LangChain + Groq.

Dois modos de operação:
    💬 Chat analítico  — responde perguntas sobre dados do CRM (deals, contatos)
    📋 Extração de lead — extrai dados estruturados de uma conversa e cria
                          contato no HubSpot automaticamente

Fluxo do chat analítico:
    pergunta → contexto dos dados (deals + contatos) → LLM → resposta em PT/EN

Fluxo de extração:
    conversa → LLM extrai nome/email/telefone/intenção → create_contact()

Não usa ferramentas/tools do LangChain por simplicidade —
o agente recebe os dados como contexto no prompt (RAG simples sobre dados estruturados).
Isso é suficiente para MVP e mais fácil de entender e explicar para clientes.
"""

import json
import logging
import os

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from hubspot_client import get_contacts, get_deals, create_contact

log = logging.getLogger(__name__)

GROQ_MODEL = "llama-3.3-70b-versatile"


# ══════════════════════════════════════════════════════════════════════════════
# LLM
# ══════════════════════════════════════════════════════════════════════════════

def get_llm(temperature: float = 0.3) -> ChatGroq:
    return ChatGroq(
        model=GROQ_MODEL,
        temperature=temperature,
        max_tokens=1024,
        api_key=os.getenv("GROQ_API_KEY"),
    )


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — contexto para o LLM
# ══════════════════════════════════════════════════════════════════════════════

def _resumir_deals(deals: list[dict]) -> str:
    """Serializa deals em texto compacto para o prompt."""
    if not deals:
        return "Nenhum deal encontrado no CRM."
    linhas = []
    for d in deals:
        linhas.append(
            f"- {d['nome']} | Estágio: {d['estagio']} | "
            f"Valor: R$ {d['valor']:,.0f} | Criado: {d['criado_em']}"
        )
    return "\n".join(linhas)


def _resumir_contatos(contatos: list[dict]) -> str:
    """Serializa contatos em texto compacto para o prompt."""
    if not contatos:
        return "Nenhum contato encontrado no CRM."
    linhas = []
    for c in contatos:
        linhas.append(
            f"- {c['nome']} | Email: {c['email']} | "
            f"Status: {c['status_lead'] or 'N/A'} | Criado: {c['criado_em']}"
        )
    return "\n".join(linhas)


# ══════════════════════════════════════════════════════════════════════════════
# MODO 1 — CHAT ANALÍTICO
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_ANALITICO = """Você é um assistente de CRM inteligente integrado ao HubSpot.
Você tem acesso aos dados reais de deals (oportunidades de venda) e contatos do CRM.
Responda de forma clara, objetiva e profissional.
Use formatação markdown quando ajudar na leitura.
Se o usuário pedir um gráfico ou análise visual, diga que vai gerar — o sistema
fará isso automaticamente após sua resposta textual.
Responda no mesmo idioma da pergunta (PT-BR ou EN).
Nunca invente dados — use apenas o que está no contexto fornecido."""


def responder_chat(
    pergunta: str,
    historico: list[dict],
    deals: list[dict] | None = None,
    contatos: list[dict] | None = None,
) -> str:
    """
    Responde uma pergunta sobre os dados do CRM.

    Parâmetros
    ----------
    pergunta   : mensagem atual do usuário
    historico  : lista de dicts {"role": "user"|"assistant", "content": str}
    deals      : lista de deals (se None, busca da API)
    contatos   : lista de contatos (se None, busca da API)

    Retorna a resposta como string markdown.
    """
    if deals is None:
        deals = get_deals()
    if contatos is None:
        contatos = get_contacts()

    contexto = f"""
=== DEALS NO CRM ({len(deals)} total) ===
{_resumir_deals(deals)}

=== CONTATOS NO CRM ({len(contatos)} total) ===
{_resumir_contatos(contatos)}
"""

    system = f"{SYSTEM_ANALITICO}\n\nDADOS ATUAIS DO CRM:\n{contexto}"

    mensagens = [SystemMessage(content=system)]

    # Inclui últimas 6 trocas do histórico para contexto de conversa
    for msg in historico[-6:]:
        if msg["role"] == "user":
            mensagens.append(HumanMessage(content=msg["content"]))
        else:
            from langchain_core.messages import AIMessage
            mensagens.append(AIMessage(content=msg["content"]))

    mensagens.append(HumanMessage(content=pergunta))

    llm = get_llm(temperature=0.3)
    resposta = llm.invoke(mensagens)
    return resposta.content.strip()


# ══════════════════════════════════════════════════════════════════════════════
# MODO 2 — EXTRAÇÃO DE LEAD E CRIAÇÃO NO HUBSPOT
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_EXTRACAO = """Você é um assistente de vendas que captura leads via chat.
Seu objetivo: conversar naturalmente com o visitante e coletar:
    - Nome completo
    - E-mail
    - Telefone (opcional)
    - Interesse / necessidade principal

Seja amigável e natural. Não pareça um formulário.
Quando tiver nome + e-mail + interesse, encerre com uma mensagem
confirmando que um especialista vai entrar em contato.

IMPORTANTE: quando tiver dados suficientes para criar o contato,
inclua no FINAL da sua resposta exatamente este bloco JSON (sem markdown):
LEAD_CAPTURADO:{"nome":"...","email":"...","telefone":"...","interesse":"..."}

Antes de ter todos os dados, converse normalmente sem o bloco JSON."""


def chat_captura_lead(
    mensagem: str,
    historico: list[dict],
) -> tuple[str, dict | None]:
    """
    Conversa de captura de lead.

    Retorna (resposta_texto, lead_dict | None).
    Se lead_dict não for None, o lead foi capturado e deve ser criado no HubSpot.
    """
    mensagens = [SystemMessage(content=SYSTEM_EXTRACAO)]

    for msg in historico[-8:]:
        if msg["role"] == "user":
            mensagens.append(HumanMessage(content=msg["content"]))
        else:
            from langchain_core.messages import AIMessage
            mensagens.append(AIMessage(content=msg["content"]))

    mensagens.append(HumanMessage(content=mensagem))

    llm = get_llm(temperature=0.5)
    resposta_raw = llm.invoke(mensagens).content.strip()

    # Tenta extrair o bloco JSON de lead capturado
    lead = None
    resposta_limpa = resposta_raw

    if "LEAD_CAPTURADO:" in resposta_raw:
        try:
            partes = resposta_raw.split("LEAD_CAPTURADO:", 1)
            resposta_limpa = partes[0].strip()
            lead_json = partes[1].strip()
            lead = json.loads(lead_json)
            log.info(f"Lead capturado pelo agente: {lead}")
        except (json.JSONDecodeError, IndexError) as e:
            log.warning(f"Falha ao parsear lead JSON: {e}")
            lead = None

    return resposta_limpa, lead


def processar_lead(lead: dict) -> dict:
    """
    Recebe lead extraído pelo agente e cria contato no HubSpot.

    Retorna o contato criado (com id da HubSpot).
    """
    resumo = f"Interesse: {lead.get('interesse', 'N/A')}"
    if lead.get("telefone"):
        resumo += f" | Telefone informado: {lead['telefone']}"

    return create_contact(
        nome=lead.get("nome", "Lead sem nome"),
        email=lead.get("email", ""),
        telefone=lead.get("telefone", ""),
        resumo_conversa=resumo,
    )


# ══════════════════════════════════════════════════════════════════════════════
# UTILITÁRIO — detecta se pergunta pede gráfico
# ══════════════════════════════════════════════════════════════════════════════

PALAVRAS_GRAFICO = [
    "gráfico", "grafico", "chart", "dashboard", "visualiz",
    "mostrar", "exibir", "plot", "funil", "pipeline",
    "por mês", "por mes", "evolução", "evolucao", "histórico",
]

def pergunta_pede_grafico(texto: str) -> bool:
    """Heurística simples para detectar se o usuário quer um gráfico."""
    texto_lower = texto.lower()
    return any(p in texto_lower for p in PALAVRAS_GRAFICO)