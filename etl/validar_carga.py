import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
TABELA = "fato_microcredito"


def tabela_md(headers, rows) -> str:
    linhas = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for r in rows:
        linhas.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    return "\n".join(linhas)


def consulta(cur, sql: str):
    cur.execute(sql)
    headers = [d[0] for d in cur.description]
    return headers, cur.fetchall()


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL nao definida. Configure o .env.")
        sys.exit(1)

    kwargs = {} if "sslmode=" in url else {"sslmode": "require"}
    conn = psycopg2.connect(url, **kwargs)
    cur = conn.cursor()

    secoes = [
        ("Volume armazenado", f"""
            SELECT COUNT(*) AS linhas,
                   pg_size_pretty(pg_relation_size('{TABELA}'))        AS so_dados,
                   pg_size_pretty(pg_total_relation_size('{TABELA}'))  AS tabela_com_indices,
                   pg_size_pretty(pg_database_size(current_database())) AS banco_inteiro
            FROM {TABELA}
        """),
        ("Periodo coberto", f"""
            SELECT MIN(data_base) AS primeira_data_base,
                   MAX(data_base) AS ultima_data_base,
                   COUNT(DISTINCT data_base) AS meses_distintos
            FROM {TABELA}
        """),
        ("Linhas por ano", f"""
            SELECT EXTRACT(YEAR FROM data_base)::int AS ano, COUNT(*) AS linhas
            FROM {TABELA} GROUP BY 1 ORDER BY 1
        """),
        ("Linhas por UF", f"""
            SELECT uf, COUNT(*) AS linhas
            FROM {TABELA} GROUP BY 1 ORDER BY 2 DESC
        """),
        ("Contagem de operacoes suprimida (-1 na origem)", f"""
            SELECT COUNT(*) FILTER (WHERE ops_suprimido) AS linhas_suprimidas,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE ops_suprimido) / NULLIF(COUNT(*), 0), 1) AS pct_do_total,
                   COUNT(*) FILTER (WHERE numero_de_operacoes < 0) AS ainda_negativas_deve_ser_0,
                   COUNT(*) FILTER (WHERE ops_suprimido AND numero_de_operacoes IS NOT NULL) AS flag_sem_null_deve_ser_0
            FROM {TABELA}
        """),
        ("Nulos em colunas-chave", f"""
            SELECT COUNT(*) FILTER (WHERE data_base IS NULL)           AS data_base,
                   COUNT(*) FILTER (WHERE uf IS NULL)                  AS uf,
                   COUNT(*) FILTER (WHERE segmento IS NULL)            AS segmento,
                   COUNT(*) FILTER (WHERE cliente IS NULL)             AS cliente,
                   COUNT(*) FILTER (WHERE porte IS NULL)               AS porte,
                   COUNT(*) FILTER (WHERE numero_de_operacoes IS NULL) AS numero_de_operacoes,
                   COUNT(*) FILTER (WHERE carteira_ativa IS NULL)      AS carteira_ativa
            FROM {TABELA}
        """),
        ("Estrutura da tabela (campos e tipos)", f"""
            SELECT column_name AS coluna,
                   data_type ||
                   CASE
                     WHEN character_maximum_length IS NOT NULL THEN '(' || character_maximum_length || ')'
                     WHEN data_type = 'numeric' THEN '(' || numeric_precision || ',' || numeric_scale || ')'
                     ELSE ''
                   END AS tipo,
                   is_nullable AS aceita_nulo
            FROM information_schema.columns
            WHERE table_name = '{TABELA}'
            ORDER BY ordinal_position
        """),
        ("Indices e constraints", f"""
            SELECT 'indice' AS tipo, indexname AS nome, indexdef AS definicao
            FROM pg_indexes WHERE tablename = '{TABELA}'
            UNION ALL
            SELECT 'constraint', conname, pg_get_constraintdef(oid)
            FROM pg_constraint WHERE conrelid = '{TABELA}'::regclass
        """),
    ]

    md = [
        "# Evidencias do banco de dados",
        "",
        f"Gerado automaticamente por `etl/validar_carga.py` em {datetime.now():%d/%m/%Y %H:%M}.",
        f"Tabela: `{TABELA}`.",
        "",
    ]
    for titulo, sql in secoes:
        headers, rows = consulta(cur, sql)
        md += [f"## {titulo}", "", tabela_md(headers, rows), ""]

    cur.close()
    conn.close()

    DOCS_DIR.mkdir(exist_ok=True)
    destino = DOCS_DIR / "evidencias_banco.md"
    destino.write_text("\n".join(md), encoding="utf-8")
    print(f"Evidencias salvas em {destino}")


if __name__ == "__main__":
    main()
