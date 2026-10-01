import streamlit as st
import plotly.graph_objects as go
from queries import (
    METRIC_SQL,
    get_filter_options,
    get_kpis,
    get_evolucao_anual,
    get_por_uf,
    get_por_porte,
)

st.set_page_config(
    page_title="Microcredito BR",
    page_icon="💳",
    layout="wide",
)

opts = get_filter_options()

with st.sidebar:
    st.title("Filtros")

    anos = st.slider("Periodo", 2021, 2026, (2021, 2026))
    ufs_sel = st.multiselect("UF", opts["ufs"], placeholder="Todos os estados")
    seg_sel = st.multiselect("Segmento", opts["segmentos"], placeholder="Todos")
    porte_sel = st.multiselect("Porte", opts["portes"], placeholder="Todos")
    cliente_sel = st.radio("Cliente", ["Ambos", "PF", "PJ"])

    st.divider()
    st.caption("Metrica principal")
    metrica = st.radio(
        "Metrica",
        list(METRIC_SQL.keys()),
        index=0,
        label_visibility="collapsed",
    )

filtros = {
    "ano_inicio": anos[0],
    "ano_fim":    anos[1],
    "ufs":        ufs_sel or [],
    "segmentos":  seg_sel or [],
    "portes":     porte_sel or [],
    "cliente":    cliente_sel,
}

st.title("Microcredito no Brasil")
st.caption(f"SCR.data - Banco Central do Brasil · {anos[0]} a {anos[1]}")

kpis = get_kpis(filtros)
atual = kpis["atual"]
ant = kpis["anterior"]


def variacao(v_atual, v_ant):
    if not v_ant:
        return None
    return (v_atual - v_ant) / abs(v_ant) * 100


def fmt_delta(pct):
    if pct is None:
        return None
    sinal = "+" if pct >= 0 else ""
    return f"{sinal}{pct:.1f}% vs ano anterior"


c1, c2, c3, c4 = st.columns(4)

with c1:
    v = atual["carteira_ativa"]
    st.metric("Carteira Ativa", f"R$ {v/1e9:.2f}B", fmt_delta(variacao(v, ant["carteira_ativa"])))

with c2:
    v = atual["inadimplencia_pct"]
    delta_pct = variacao(v, ant["inadimplencia_pct"])
    st.metric("Inadimplencia", f"{v:.2f}%", fmt_delta(delta_pct), delta_color="inverse")

with c3:
    v = atual["num_operacoes"]
    st.metric("Num. Operacoes", f"{v:,.0f}", fmt_delta(variacao(v, ant["num_operacoes"])))

with c4:
    v = atual["ticket_medio"]
    st.metric("Ticket Medio", f"R$ {v:,.0f}", fmt_delta(variacao(v, ant["ticket_medio"])))

st.divider()
metrica_sql = METRIC_SQL[metrica]

# Grafico 1: evolucao anual
evolucao = get_evolucao_anual(metrica_sql, filtros)
if evolucao:
    anos_vals = [r["ano"] for r in evolucao]
    vals = [r["valor"] for r in evolucao]
    media = sum(vals) / len(vals) if vals else 0
    cores = ["#4ade80" if v >= media else "#3b82f6" for v in vals]

    fig_ev = go.Figure(go.Bar(
        x=anos_vals,
        y=vals,
        marker_color=cores,
        hovertemplate="Ano: %{x}<br>%{y:,.2f}<extra></extra>",
    ))
    fig_ev.update_layout(
        title=f"Evolucao anual — {metrica}",
        xaxis_title="Ano",
        yaxis_title=metrica,
        plot_bgcolor="#1e293b",
        paper_bgcolor="#0f172a",
        font_color="#e2e8f0",
        height=280,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    fig_ev.update_xaxes(tickvals=anos_vals, gridcolor="#334155")
    fig_ev.update_yaxes(gridcolor="#334155")
    st.plotly_chart(fig_ev, use_container_width=True)
else:
    st.info("Sem dados para o periodo e filtros selecionados.")

# Graficos 2 e 3: UF e porte lado a lado
col_uf, col_porte = st.columns(2)

with col_uf:
    por_uf = get_por_uf(metrica_sql, filtros)
    if por_uf:
        ufs_labels = [r["uf"] for r in reversed(por_uf)]
        vals_uf = [r["valor"] for r in reversed(por_uf)]
        fig_uf = go.Figure(go.Bar(
            x=vals_uf,
            y=ufs_labels,
            orientation="h",
            marker_color="#3b82f6",
            hovertemplate="%{y}: %{x:,.2f}<extra></extra>",
        ))
        fig_uf.update_layout(
            title=f"Top 10 UFs — {metrica}",
            plot_bgcolor="#1e293b",
            paper_bgcolor="#0f172a",
            font_color="#e2e8f0",
            height=320,
            margin=dict(l=0, r=0, t=40, b=0),
        )
        fig_uf.update_xaxes(gridcolor="#334155")
        fig_uf.update_yaxes(gridcolor="#334155")
        st.plotly_chart(fig_uf, use_container_width=True)

with col_porte:
    por_porte = get_por_porte(metrica_sql, filtros)
    if por_porte:
        portes_labels = [r["porte"][:20] for r in por_porte]
        vals_porte = [r["valor"] for r in por_porte]
        fig_porte = go.Figure(go.Bar(
            x=portes_labels,
            y=vals_porte,
            marker_color="#fbbf24",
            hovertemplate="%{x}: %{y:,.2f}<extra></extra>",
        ))
        fig_porte.update_layout(
            title=f"Por Porte — {metrica}",
            plot_bgcolor="#1e293b",
            paper_bgcolor="#0f172a",
            font_color="#e2e8f0",
            height=320,
            margin=dict(l=0, r=0, t=40, b=0),
        )
        fig_porte.update_xaxes(tickangle=-35, gridcolor="#334155")
        fig_porte.update_yaxes(gridcolor="#334155")
        st.plotly_chart(fig_porte, use_container_width=True)
