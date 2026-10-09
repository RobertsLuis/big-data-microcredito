import os
import psycopg2
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Todas as medidas abaixo sao POSICAO (estoque) na data-base: nunca somar meses.
METRIC_SQL = {
    "Num. Operacoes":    "SUM(numero_de_operacoes)",
    "Carteira Ativa":    "SUM(carteira_ativa)",
    "Inadimplencia (%)": "ROUND(SUM(carteira_inadimplencia)::numeric / NULLIF(SUM(carteira_ativa), 0) * 100, 2)",
    # exclui da carteira as linhas sem contagem de operacoes, senao o ticket fica distorcido
    "Ticket Medio (R$)": "ROUND(SUM(carteira_ativa) FILTER (WHERE numero_de_operacoes IS NOT NULL)::numeric "
                         "/ NULLIF(SUM(numero_de_operacoes), 0), 2)",
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


def _dim_filters(filtros: dict, params: list) -> str:
    """Filtros de dimensao (sem data). Acrescenta os valores em params, na ordem dos %s."""
    clauses = ["TRUE"]
    if filtros.get("ufs"):
        clauses.append("uf = ANY(%s)")
        params.append(filtros["ufs"])
    if filtros.get("segmentos"):
        clauses.append("segmento = ANY(%s)")
        params.append(filtros["segmentos"])
    if filtros.get("portes"):
        clauses.append("porte = ANY(%s)")
        params.append(filtros["portes"])
    if filtros.get("cliente") and filtros["cliente"] != "Ambos":
        clauses.append("cliente = %s")
        params.append(filtros["cliente"])
    return " AND ".join(clauses)


def _data_ref(cur, ano_inicio: int, ano_fim: int):
    """Ultima data-base disponivel dentro do periodo escolhido."""
    cur.execute(
        "SELECT MAX(data_base) FROM fato_microcredito "
        "WHERE EXTRACT(YEAR FROM data_base) BETWEEN %s AND %s",
        (ano_inicio, ano_fim),
    )
    return cur.fetchone()[0]


def _data_mesmo_mes_ano_anterior(cur, data_ref):
    """Data-base do mesmo mes, um ano antes (None se nao existir)."""
    if data_ref is None:
        return None
    cur.execute(
        "SELECT MAX(data_base) FROM fato_microcredito "
        "WHERE date_trunc('month', data_base) = date_trunc('month', %s::date - INTERVAL '12 months')",
        (data_ref,),
    )
    return cur.fetchone()[0]


def _snapshot_where(cur, filtros: dict, params: list) -> str:
    params.append(_data_ref(cur, filtros["ano_inicio"], filtros["ano_fim"]))
    return "data_base = %s AND " + _dim_filters(filtros, params)


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


def _fetch_kpi_block(cur, data_base, filtros: dict) -> dict:
    if data_base is None:
        return {"carteira_ativa": 0.0, "inadimplencia_pct": 0.0, "num_operacoes": 0, "ticket_medio": 0.0}
    params = [data_base]
    dim = _dim_filters(filtros, params)
    ticket_sql = METRIC_SQL["Ticket Medio (R$)"]
    cur.execute(f"""
        SELECT
            SUM(carteira_ativa),
            ROUND(SUM(carteira_inadimplencia)::numeric / NULLIF(SUM(carteira_ativa), 0) * 100, 2),
            SUM(numero_de_operacoes),
            {ticket_sql}
        FROM fato_microcredito
        WHERE data_base = %s AND {dim}
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
    data_ref = _data_ref(cur, filtros["ano_inicio"], filtros["ano_fim"])
    data_ant = _data_mesmo_mes_ano_anterior(cur, data_ref)
    atual = _fetch_kpi_block(cur, data_ref, filtros)
    anterior = _fetch_kpi_block(cur, data_ant, filtros)
    conn.close()
    return {"atual": atual, "anterior": anterior, "data_ref": data_ref, "data_ant": data_ant}


@st.cache_data(ttl=3600)
def get_evolucao_anual(metrica_sql: str, filtros: dict) -> list:
    """Uma posicao por ano: a ultima data-base disponivel de cada ano."""
    params = [filtros["ano_inicio"], filtros["ano_fim"]]
    dim = _dim_filters(filtros, params)
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT EXTRACT(YEAR FROM data_base)::int AS ano, {metrica_sql} AS valor
        FROM fato_microcredito
        WHERE data_base IN (
            SELECT MAX(data_base) FROM fato_microcredito
            WHERE EXTRACT(YEAR FROM data_base) BETWEEN %s AND %s
            GROUP BY EXTRACT(YEAR FROM data_base)
        ) AND {dim}
        GROUP BY ano
        ORDER BY ano
    """, params)
    rows = [{"ano": r[0], "valor": float(r[1] or 0)} for r in cur.fetchall()]
    conn.close()
    return rows


@st.cache_data(ttl=3600)
def get_por_uf(metrica_sql: str, filtros: dict) -> list:
    conn = _get_conn()
    cur = conn.cursor()
    params = []
    where = _snapshot_where(cur, filtros, params)
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
    conn = _get_conn()
    cur = conn.cursor()
    params = []
    where = _snapshot_where(cur, filtros, params)
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
