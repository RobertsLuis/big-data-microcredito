import os
import psycopg2
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

METRIC_SQL = {
    "Num. Operacoes":    "SUM(numero_de_operacoes)",
    "Carteira Ativa":    "SUM(carteira_ativa)",
    "Inadimplencia (%)": "ROUND(SUM(carteira_inadimplencia)::numeric / NULLIF(SUM(carteira_ativa), 0) * 100, 2)",
    "Ticket Medio (R$)": "ROUND(SUM(carteira_ativa)::numeric / NULLIF(SUM(numero_de_operacoes), 0), 2)",
}


def _get_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        try:
            url = st.secrets["DATABASE_URL"]
        except Exception:
            pass
    if not url:
        raise RuntimeError("DATABASE_URL nao configurado.")
    return psycopg2.connect(url)


def _build_where(filtros: dict, params: list, alias: str = "") -> str:
    col = lambda c: f"{alias}.{c}" if alias else c
    clauses = [f"EXTRACT(YEAR FROM {col('data_base')}) BETWEEN %s AND %s"]
    params.extend([filtros["ano_inicio"], filtros["ano_fim"]])

    if filtros.get("ufs"):
        clauses.append(f"{col('uf')} = ANY(%s)")
        params.append(filtros["ufs"])
    if filtros.get("segmentos"):
        clauses.append(f"{col('segmento')} = ANY(%s)")
        params.append(filtros["segmentos"])
    if filtros.get("portes"):
        clauses.append(f"{col('porte')} = ANY(%s)")
        params.append(filtros["portes"])
    if filtros.get("cliente") and filtros["cliente"] != "Ambos":
        clauses.append(f"{col('cliente')} = %s")
        params.append(filtros["cliente"])

    return " AND ".join(clauses)


@st.cache_data(ttl=3600)
def get_filter_options() -> dict:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT uf FROM fato_microcredito WHERE uf IS NOT NULL ORDER BY 1")
    ufs = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT segmento FROM fato_microcredito WHERE segmento IS NOT NULL ORDER BY 1")
    segmentos = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT porte FROM fato_microcredito WHERE porte IS NOT NULL ORDER BY 1")
    portes = [r[0] for r in cur.fetchall()]
    conn.close()
    return {"ufs": ufs, "segmentos": segmentos, "portes": portes}


def _fetch_kpi_block(cur, where: str, params: list) -> dict:
    cur.execute(f"""
        SELECT
            SUM(carteira_ativa)                                                              AS carteira_ativa,
            ROUND(SUM(carteira_inadimplencia)::numeric / NULLIF(SUM(carteira_ativa), 0) * 100, 2) AS inadimplencia_pct,
            SUM(numero_de_operacoes)                                                         AS num_operacoes,
            ROUND(SUM(carteira_ativa)::numeric / NULLIF(SUM(numero_de_operacoes), 0), 2)    AS ticket_medio
        FROM fato_microcredito
        WHERE {where}
    """, params)
    row = cur.fetchone()
    return {
        "carteira_ativa":    float(row[0] or 0),
        "inadimplencia_pct": float(row[1] or 0),
        "num_operacoes":     int(row[2] or 0),
        "ticket_medio":      float(row[3] or 0),
    }


@st.cache_data(ttl=3600)
def get_kpis(filtros: dict) -> dict:
    conn = _get_conn()
    cur = conn.cursor()

    params_atual = []
    where_atual = _build_where(filtros, params_atual)
    atual = _fetch_kpi_block(cur, where_atual, params_atual)

    filtros_ant = {**filtros, "ano_inicio": filtros["ano_inicio"] - 1, "ano_fim": filtros["ano_fim"] - 1}
    params_ant = []
    where_ant = _build_where(filtros_ant, params_ant)
    anterior = _fetch_kpi_block(cur, where_ant, params_ant)

    conn.close()
    return {"atual": atual, "anterior": anterior}


@st.cache_data(ttl=3600)
def get_evolucao_anual(metrica_sql: str, filtros: dict) -> list:
    params = []
    where = _build_where(filtros, params)
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT EXTRACT(YEAR FROM data_base)::int AS ano, {metrica_sql} AS valor
        FROM fato_microcredito
        WHERE {where}
        GROUP BY ano
        ORDER BY ano
    """, params)
    rows = [{"ano": r[0], "valor": float(r[1] or 0)} for r in cur.fetchall()]
    conn.close()
    return rows


@st.cache_data(ttl=3600)
def get_por_uf(metrica_sql: str, filtros: dict) -> list:
    params = []
    where = _build_where(filtros, params)
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT uf, {metrica_sql} AS valor
        FROM fato_microcredito
        WHERE {where} AND uf IS NOT NULL
        GROUP BY uf
        ORDER BY valor DESC
        LIMIT 10
    """, params)
    rows = [{"uf": r[0], "valor": float(r[1] or 0)} for r in cur.fetchall()]
    conn.close()
    return rows


@st.cache_data(ttl=3600)
def get_por_porte(metrica_sql: str, filtros: dict) -> list:
    params = []
    where = _build_where(filtros, params)
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT porte, {metrica_sql} AS valor
        FROM fato_microcredito
        WHERE {where} AND porte IS NOT NULL
        GROUP BY porte
        ORDER BY valor DESC
    """, params)
    rows = [{"porte": r[0], "valor": float(r[1] or 0)} for r in cur.fetchall()]
    conn.close()
    return rows
