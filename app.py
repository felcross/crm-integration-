"""
app.py — Interface principal do CRM AI MVP.

Modos:
    📊 Dashboard      — métricas e gráficos dos dados reais do HubSpot
    🔍 Chat Analítico — perguntas em linguagem natural sobre os dados do CRM
    🎯 Captura de Lead — fluxo guiado que cria contato no HubSpot
"""

import logging
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import analytics
import ai_agent
from hubspot_client import get_contacts, get_deals, invalidar_tudo, health_check

load_dotenv()
logging.basicConfig(level=logging.INFO)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="CRM AI Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .stChatMessage { background: transparent !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════

def _init_state():
    defaults = {
        "messages_analitico": [],
        "messages_lead":      [],
        "modo":               "📊 Dashboard",
        "lead_criado":        None,
        "lead_iniciado":      False,   # controla o botão de iniciar atendimento
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados():
    return get_deals(), get_contacts()


def _grafico_para_pergunta(pergunta: str, deals: list, contatos: list):
    texto = pergunta.lower()
    if "funil" in texto:
        return analytics.grafico_funil(deals), "Funil de Vendas"
    if any(p in texto for p in ["estágio", "estagio", "stage", "pipeline"]):
        return analytics.grafico_deals_por_estagio(deals), "Deals por Estágio"
    if any(p in texto for p in ["mês", "mes", "month", "evolução", "histórico"]):
        return analytics.grafico_valor_por_mes(deals), "Valor por Mês"
    if any(p in texto for p in ["contato", "contact", "lead"]):
        return analytics.grafico_contatos_por_mes(contatos), "Contatos por Mês"
    return analytics.grafico_deals_por_estagio(deals), "Deals por Estágio"


# ══════════════════════════════════════════════════════════════════════════════
# CARREGA DADOS — sempre, independente do modo
# ══════════════════════════════════════════════════════════════════════════════

try:
    deals, contatos = carregar_dados()
    dados_ok = True
except Exception as e:
    deals, contatos = [], []
    dados_ok = False
    st.warning(f"⚠️ Não foi possível carregar dados do HubSpot: {e}")

resumo_deals    = analytics.resumo_deals(deals)
resumo_contatos = analytics.resumo_contatos(contatos)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("🤖 CRM AI MVP")
    st.caption("Integração inteligente com HubSpot")
    st.divider()

    # Status — conta da lista real, não do health_check
    if dados_ok:
        st.success(f"✅ HubSpot conectado · {len(contatos)} contatos · {len(deals)} deals")
    else:
        st.error("❌ Sem conexão com HubSpot")

    st.divider()

    # Navegação — 3 opções diretas, sem sub-menu
    st.session_state.modo = st.radio(
        "Navegação",
        ["📊 Dashboard", "🔍 Chat Analítico", "🎯 Captura de Lead"],
        index=["📊 Dashboard", "🔍 Chat Analítico", "🎯 Captura de Lead"].index(
            st.session_state.modo
        ),
    )

    st.divider()

    if st.button("🔄 Atualizar dados", use_container_width=True, type="primary"):
        invalidar_tudo()
        st.cache_data.clear()
        st.rerun()

    if st.button("🗑️ Limpar conversas", use_container_width=True):
        st.session_state.messages_analitico = []
        st.session_state.messages_lead      = []
        st.session_state.lead_criado        = None
        st.session_state.lead_iniciado      = False
        st.rerun()

    st.divider()
    st.caption("Python · LangChain · Groq · HubSpot API · Plotly")


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.modo == "📊 Dashboard":

    st.header("📊 Dashboard CRM")
    st.caption("Dados em tempo real da sua conta HubSpot · Cache de 5 minutos")

    # Métricas
    st.subheader("Visão Geral")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de Deals",      resumo_deals["total_deals"])
    col2.metric("Valor do Pipeline",   f"R$ {resumo_deals['valor_total']:,.0f}")
    col3.metric("Ticket Médio",        f"R$ {resumo_deals['ticket_medio']:,.0f}")
    col4.metric(
        "Deals Fechados",
        resumo_deals["deals_fechados"],
        delta=f"R$ {resumo_deals['valor_fechado']:,.0f}",
    )

    st.divider()

    # Gráficos linha 1
    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(analytics.grafico_deals_por_estagio(deals), use_container_width=True)
    with col_b:
        st.plotly_chart(analytics.grafico_funil(deals), use_container_width=True)

    # Gráficos linha 2
    col_c, col_d = st.columns(2)
    with col_c:
        st.plotly_chart(analytics.grafico_valor_por_mes(deals), use_container_width=True)
    with col_d:
        st.plotly_chart(analytics.grafico_contatos_por_mes(contatos), use_container_width=True)

    st.divider()

    # Tabelas
    st.subheader("📋 Todos os Deals")
    if deals:
        df_t = pd.DataFrame(deals)[["nome", "valor", "estagio", "pipeline", "criado_em"]]
        df_t.columns = ["Nome", "Valor (R$)", "Estágio", "Pipeline", "Criado em"]
        df_t["Valor (R$)"] = df_t["Valor (R$)"].apply(lambda x: f"R$ {x:,.0f}")
        st.dataframe(df_t, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum deal encontrado.")

    st.subheader("👥 Contatos")
    if contatos:
        df_c = pd.DataFrame(contatos)[["nome", "email", "status_lead", "criado_em"]]
        df_c.columns = ["Nome", "Email", "Status", "Criado em"]
        st.dataframe(df_c, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum contato encontrado.")


# ══════════════════════════════════════════════════════════════════════════════
# CHAT ANALÍTICO
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.modo == "🔍 Chat Analítico":

    st.header("🔍 Chat Analítico")
    st.caption("Perguntas em linguagem natural sobre os dados do seu CRM.")

    historico = st.session_state.messages_analitico

    # Renderiza histórico
    for msg in historico:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("grafico"):
                st.plotly_chart(msg["grafico"], use_container_width=True)

    # Sugestões — só quando histórico vazio
    if not historico:
        st.markdown("**💡 Sugestões de perguntas:**")
        sugestoes = [
            "Quantos deals temos no pipeline?",
            "Qual o valor total dos deals fechados?",
            "Me mostra um gráfico dos deals por estágio",
            "Qual o ticket médio dos nossos deals?",
            "Mostra o funil de vendas",
        ]
        cols = st.columns(len(sugestoes))
        for i, sug in enumerate(sugestoes):
            if cols[i].button(sug, key=f"sug_{i}", use_container_width=True):
                st.session_state.messages_analitico.append({"role": "user", "content": sug})
                with st.spinner("Consultando dados..."):
                    resposta = ai_agent.responder_chat(sug, [], deals, contatos)
                grafico = None
                if ai_agent.pergunta_pede_grafico(sug):
                    fig, _ = _grafico_para_pergunta(sug, deals, contatos)
                    grafico = fig
                st.session_state.messages_analitico.append({
                    "role": "assistant", "content": resposta, "grafico": grafico
                })
                st.rerun()

    # Input de chat
    pergunta = st.chat_input("Ex: Qual o valor total do pipeline?")

    if pergunta:
        historico.append({"role": "user", "content": pergunta})
        with st.spinner("Consultando dados..."):
            resposta = ai_agent.responder_chat(pergunta, historico[:-1], deals, contatos)
        grafico = None
        if ai_agent.pergunta_pede_grafico(pergunta):
            fig, _ = _grafico_para_pergunta(pergunta, deals, contatos)
            grafico = fig
        historico.append({"role": "assistant", "content": resposta, "grafico": grafico})
        st.session_state.messages_analitico = historico
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# CAPTURA DE LEAD
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.modo == "🎯 Captura de Lead":

    st.header("🎯 Captura de Lead")
    st.caption(
        "Simule o chat de atendimento do seu site. "
        "O bot coleta nome, e-mail e interesse — e cria o contato no HubSpot automaticamente."
    )

    # Banner de lead criado
    if st.session_state.lead_criado:
        lead = st.session_state.lead_criado
        nome_criado = (
            f"{lead.get('properties', {}).get('firstname', '')} "
            f"{lead.get('properties', {}).get('lastname', '')}".strip()
        )
        st.success(
            f"✅ **Lead criado no HubSpot!** "
            f"Nome: **{nome_criado}** · ID: `{lead.get('id')}`"
        )
        if st.button("🔄 Novo atendimento"):
            st.session_state.messages_lead = []
            st.session_state.lead_criado   = None
            st.session_state.lead_iniciado = False
            st.rerun()
        st.stop()

    # Tela inicial — botão para iniciar
    if not st.session_state.lead_iniciado:
        st.markdown("---")
        col_centro, _, _ = st.columns([1, 1, 1])
        with col_centro:
            st.markdown("### 👋 Pronto para iniciar um atendimento?")
            st.markdown(
                "Clique abaixo para simular um visitante chegando no site da empresa. "
                "O assistente vai coletar os dados e registrar o lead no HubSpot."
            )
            if st.button("▶ Iniciar atendimento", type="primary", use_container_width=True):
                st.session_state.lead_iniciado = True
                # Dispara mensagem de boas-vindas do bot
                boas_vindas = (
                    "Olá! 👋 Seja bem-vindo. Sou o assistente virtual da empresa.\n\n"
                    "Para que um de nossos especialistas possa entrar em contato com você, "
                    "preciso de algumas informações.\n\n"
                    "Pode começar me dizendo seu **nome completo**?"
                )
                st.session_state.messages_lead = [
                    {"role": "assistant", "content": boas_vindas}
                ]
                st.rerun()
        st.stop()

    # Chat de atendimento
    historico_lead = st.session_state.messages_lead

    for msg in historico_lead:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    mensagem = st.chat_input("Digite sua resposta...")

    if mensagem:
        historico_lead.append({"role": "user", "content": mensagem})

        with st.spinner("Digitando..."):
            resposta, lead_data = ai_agent.chat_captura_lead(mensagem, historico_lead[:-1])

        historico_lead.append({"role": "assistant", "content": resposta})
        st.session_state.messages_lead = historico_lead

        # Lead capturado — cria no HubSpot
        if lead_data:
            with st.spinner("Registrando contato no HubSpot..."):
                try:
                    contato_criado = ai_agent.processar_lead(lead_data)
                    st.session_state.lead_criado = contato_criado
                    st.cache_data.clear()  # força reload dos contatos no dashboard
                except Exception as e:
                    st.error(f"Erro ao criar contato: {e}")

        st.rerun()