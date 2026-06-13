"""
analytics.py — Processamento de dados e geração de gráficos.

Recebe listas brutas vindas do hubspot_client, processa com Pandas
e retorna figuras Plotly prontas para st.plotly_chart().

Funções disponíveis:
    resumo_deals(deals)         → dict com métricas principais
    grafico_deals_por_estagio() → bar chart horizontal
    grafico_valor_por_mes()     → line chart de receita mensal
    grafico_funil()             → funnel chart do pipeline
    resumo_contatos(contatos)   → dict com métricas de contatos
    grafico_contatos_por_mes()  → line chart de novos contatos
"""

import logging
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

log = logging.getLogger(__name__)

# Paleta consistente com visual profissional
CORES = {
    "primaria":    "#4F46E5",   # indigo
    "secundaria":  "#06B6D4",   # cyan
    "sucesso":     "#10B981",   # emerald
    "alerta":      "#F59E0B",   # amber
    "fundo":       "#0F172A",   # slate-900
    "superficie":  "#1E293B",   # slate-800
    "texto":       "#F1F5F9",   # slate-100
}

SEQUENCIA = [
    "#4F46E5", "#06B6D4", "#10B981",
    "#F59E0B", "#EF4444", "#8B5CF6",
]

LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=CORES["texto"], family="Inter, sans-serif"),
    margin=dict(l=20, r=20, t=40, b=20),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _to_df_deals(deals: list[dict]) -> pd.DataFrame:
    if not deals:
        return pd.DataFrame(columns=["id", "nome", "valor", "estagio", "pipeline", "data_close", "criado_em"])
    df = pd.DataFrame(deals)
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0)
    for col in ["criado_em", "data_close"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    return df


def _to_df_contatos(contatos: list[dict]) -> pd.DataFrame:
    if not contatos:
        return pd.DataFrame(columns=["id", "nome", "email", "telefone", "status_lead", "criado_em"])
    df = pd.DataFrame(contatos)
    df["criado_em"] = pd.to_datetime(df["criado_em"], errors="coerce", utc=True)
    return df


def _apply_layout(fig: go.Figure, titulo: str = "") -> go.Figure:
    fig.update_layout(**LAYOUT_BASE, title=dict(text=titulo, font=dict(size=16)))
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", zeroline=False)
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# DEALS — MÉTRICAS
# ══════════════════════════════════════════════════════════════════════════════

def resumo_deals(deals: list[dict]) -> dict:
    """
    Retorna métricas principais dos deals para exibir como st.metric().

    Retorna:
        total_deals      : int
        valor_total      : float
        ticket_medio     : float
        deals_fechados   : int
        valor_fechado    : float
        estagios         : dict {estagio: contagem}
    """
    df = _to_df_deals(deals)

    if df.empty:
        return {
            "total_deals": 0, "valor_total": 0.0, "ticket_medio": 0.0,
            "deals_fechados": 0, "valor_fechado": 0.0, "estagios": {},
        }

    fechados = df[df["estagio"].str.lower().str.contains("closed|won|ganho|fechado", na=False)]

    return {
        "total_deals":    len(df),
        "valor_total":    df["valor"].sum(),
        "ticket_medio":   df["valor"].mean(),
        "deals_fechados": len(fechados),
        "valor_fechado":  fechados["valor"].sum(),
        "estagios":       df["estagio"].value_counts().to_dict(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# DEALS — GRÁFICOS
# ══════════════════════════════════════════════════════════════════════════════

def grafico_deals_por_estagio(deals: list[dict]) -> go.Figure:
    """Bar chart horizontal: quantidade de deals por estágio do pipeline."""
    df = _to_df_deals(deals)

    if df.empty or "estagio" not in df.columns:
        fig = go.Figure()
        fig.add_annotation(text="Sem deals para exibir", x=0.5, y=0.5,
                           showarrow=False, font=dict(color=CORES["texto"]))
        return _apply_layout(fig, "Deals por Estágio")

    contagem = df.groupby("estagio").size().reset_index(name="quantidade")
    contagem = contagem.sort_values("quantidade", ascending=True)

    fig = px.bar(
        contagem,
        x="quantidade",
        y="estagio",
        orientation="h",
        color="quantidade",
        color_continuous_scale=[[0, CORES["secundaria"]], [1, CORES["primaria"]]],
        text="quantidade",
    )
    fig.update_traces(textposition="outside")
    fig.update_coloraxes(showscale=False)
    return _apply_layout(fig, "Deals por Estágio")


def grafico_valor_por_mes(deals: list[dict]) -> go.Figure:
    """Line chart: valor total de deals criados por mês."""
    df = _to_df_deals(deals)

    if df.empty or df["criado_em"].isna().all():
        fig = go.Figure()
        fig.add_annotation(text="Sem dados de data para exibir", x=0.5, y=0.5,
                           showarrow=False, font=dict(color=CORES["texto"]))
        return _apply_layout(fig, "Valor por Mês")

    df = df.dropna(subset=["criado_em"])
    df["mes"] = df["criado_em"].dt.to_period("M").astype(str)
    por_mes = df.groupby("mes")["valor"].sum().reset_index()
    por_mes = por_mes.sort_values("mes")

    fig = px.line(
        por_mes,
        x="mes",
        y="valor",
        markers=True,
        color_discrete_sequence=[CORES["primaria"]],
    )
    fig.update_traces(
        line=dict(width=3),
        marker=dict(size=8, color=CORES["secundaria"]),
        fill="tozeroy",
        fillcolor="rgba(79,70,229,0.15)",
    )
    fig.update_layout(xaxis_title="Mês", yaxis_title="Valor (R$)")
    return _apply_layout(fig, "Valor Total de Deals por Mês")


def grafico_funil(deals: list[dict]) -> go.Figure:
    """Funnel chart do pipeline de vendas."""
    df = _to_df_deals(deals)

    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem deals para exibir", x=0.5, y=0.5,
                           showarrow=False, font=dict(color=CORES["texto"]))
        return _apply_layout(fig, "Funil de Vendas")

    contagem = df.groupby("estagio").agg(
        quantidade=("id", "count"),
        valor=("valor", "sum"),
    ).reset_index().sort_values("quantidade", ascending=False)

    fig = go.Figure(go.Funnel(
        y=contagem["estagio"],
        x=contagem["quantidade"],
        textinfo="value+percent initial",
        marker=dict(color=SEQUENCIA[:len(contagem)]),
    ))
    return _apply_layout(fig, "Funil de Vendas")


# ══════════════════════════════════════════════════════════════════════════════
# CONTATOS — MÉTRICAS E GRÁFICO
# ══════════════════════════════════════════════════════════════════════════════

def resumo_contatos(contatos: list[dict]) -> dict:
    """Métricas principais de contatos."""
    df = _to_df_contatos(contatos)

    if df.empty:
        return {"total": 0, "com_email": 0, "com_telefone": 0, "por_status": {}}

    return {
        "total":        len(df),
        "com_email":    df["email"].notna().sum(),
        "com_telefone": df["telefone"].notna().sum(),
        "por_status":   df["status_lead"].value_counts().to_dict(),
    }


def grafico_contatos_por_mes(contatos: list[dict]) -> go.Figure:
    """Line chart: novos contatos por mês."""
    df = _to_df_contatos(contatos)

    if df.empty or df["criado_em"].isna().all():
        fig = go.Figure()
        fig.add_annotation(text="Sem dados suficientes", x=0.5, y=0.5,
                           showarrow=False, font=dict(color=CORES["texto"]))
        return _apply_layout(fig, "Novos Contatos por Mês")

    df = df.dropna(subset=["criado_em"])
    df["mes"] = df["criado_em"].dt.to_period("M").astype(str)
    por_mes = df.groupby("mes").size().reset_index(name="contatos")

    fig = px.bar(
        por_mes,
        x="mes",
        y="contatos",
        color_discrete_sequence=[CORES["sucesso"]],
        text="contatos",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(xaxis_title="Mês", yaxis_title="Novos Contatos")
    return _apply_layout(fig, "Novos Contatos por Mês")