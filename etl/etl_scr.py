"""
ETL - SCR.data (Banco Central) - Microcredito
Filtra submodalidade == 'Microcrédito', converte tipos, salva parquet e carrega no PostgreSQL Aiven.

Alem da base tratada, gera evidencias para a documentacao em docs/:
  - relatorio_etl.json     : arquivos de origem (nome, tamanho, SHA-256), linhas por CSV e por etapa
  - amostra_original.csv   : 20 linhas sorteadas (seed fixa) como chegaram do BCB
  - amostra_tratada.csv    : as mesmas linhas apos o tratamento (as que sobreviveram)

Uso:
    python etl_scr.py              # trata e salva parquet + evidencias (sem banco)
    python etl_scr.py --load-db    # idem, e carrega no banco
"""

import os
import sys
import json
import hashlib
import zipfile
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Caminhos
ETL_DIR = Path(__file__).resolve().parent
ROOT_DIR = ETL_DIR.parent
DOCS_DIR = ROOT_DIR / "docs"
SCHEMA_SQL = ROOT_DIR / "sql" / "schema.sql"
OUTPUT_PARQUET = ETL_DIR / "microcredito_tratado.parquet"

# Colunas monetarias que chegam como string com virgula decimal
MONETARY_COLS = [
    "a_vencer_ate_90_dias",
    "a_vencer_de_91_ate_360_dias",
    "a_vencer_de_361_ate_1080_dias",
    "a_vencer_de_1081_ate_1800_dias",
    "a_vencer_de_1801_ate_5400_dias",
    "a_vencer_acima_de_5400_dias",
    "carteira_a_vencer",
    "vencido_de_15_ate_90_dias",
    "vencido_acima_de_90_dias",
    "carteira_vencida",
    "carteira_ativa",
    "carteira_inadimplencia",
    "ativo_problematico",
]

# Colunas que vao para o banco (mesma ordem de sql/schema.sql)
DB_COLS = [
    "data_base", "uf", "segmento", "cliente", "cnae_ocupacao", "porte",
    "modalidade", "submodalidade", "origem", "indexador",
    "numero_de_operacoes", "ops_suprimido", *MONETARY_COLS,
]


# Utilidades

def _sha256(path: Path, bloco: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(bloco), b""):
            h.update(chunk)
    return h.hexdigest()


# Leitura

def _read_csv_from_zip(zf: zipfile.ZipFile, name: str) -> tuple[pd.DataFrame, int]:
    with zf.open(name) as raw:
        df = pd.read_csv(
            raw,
            sep=";",
            encoding="utf-8-sig",
            dtype=str,
            na_values=["", "NA", "N/A", "Indisponível"],
        )
    # Normalizar nomes de colunas (espaços)
    df.columns = [c.strip().lower() for c in df.columns]
    total = len(df)
    return df[df["submodalidade"] == "Microcrédito"].copy(), total


def extract(zip_files: list[Path]) -> tuple[pd.DataFrame, list[dict]]:
    frames = []
    por_csv = []
    for zp in zip_files:
        log.info(f"Lendo {zp.name} ...")
        with zipfile.ZipFile(zp) as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            for name in sorted(csv_names):
                chunk, total = _read_csv_from_zip(zf, name)
                log.info(f"  {name}: {len(chunk):,} de {total:,} linhas são microcrédito")
                por_csv.append({
                    "zip": zp.name,
                    "csv": name,
                    "linhas_csv": total,
                    "linhas_microcredito": len(chunk),
                })
                frames.append(chunk)
    if not frames:
        raise RuntimeError("Nenhum dado encontrado. Verifique os ZIPs no diretorio raiz.")
    return pd.concat(frames, ignore_index=True), por_csv


# Transformacao

def transform(df: pd.DataFrame, stats: dict) -> pd.DataFrame:
    log.info(f"Transformando {len(df):,} linhas ...")
    stats["linhas_apos_filtro_microcredito"] = len(df)

    # Amostra da versao ORIGINAL (strings como chegaram), com seed fixa
    DOCS_DIR.mkdir(exist_ok=True)
    amostra_idx = df.sample(min(20, len(df)), random_state=42).index
    df.loc[amostra_idx].to_csv(
        DOCS_DIR / "amostra_original.csv", sep=";", index=False, encoding="utf-8-sig"
    )

    # Data
    df["data_base"] = pd.to_datetime(df["data_base"], errors="coerce")

    # Monetários: "255.934,78" → 255934.78
    for col in MONETARY_COLS:
        if col in df.columns:
            df[col] = (
                df[col]
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
            )

    # Numero de operacoes: valor negativo (-1) nao e contagem real.
    # A Metodologia V2 do SCR.data nao documenta o -1; a equipe o interpreta como
    # contagem suprimida. Mantemos a linha (a carteira em R$ continua valida),
    # registramos a flag e deixamos a contagem como NULL.
    ops = pd.to_numeric(df["numero_de_operacoes"], errors="coerce")
    suprimido = (ops < 0).fillna(False)
    stats["numero_de_operacoes"] = {
        "linhas_menos_um": int((ops == -1).sum()),
        "linhas_negativas_total": int(suprimido.sum()),
        "linhas_zero": int((ops == 0).sum()),
        "linhas_nulas_na_origem": int(ops.isna().sum()),
        "carteira_ativa_nas_linhas_suprimidas": (
            float(df.loc[suprimido, "carteira_ativa"].sum())
            if "carteira_ativa" in df.columns else None
        ),
    }
    df["ops_suprimido"] = suprimido
    df["numero_de_operacoes"] = ops.mask(suprimido).astype("Int64")
    n_sup = int(suprimido.sum())
    log.info(f"{n_sup:,} linhas ({n_sup / len(df):.1%}) com contagem suprimida (-1) -> NULL + flag")

    # Remover nulos em chaves obrigatórias e duplicatas (contadas separadamente)
    n0 = len(df)
    nulos = df[["data_base", "uf", "segmento"]].isna().any(axis=1)
    df = df.loc[~nulos]
    n1 = len(df)
    df = df.drop_duplicates()
    stats["removidas_por_nulo_em_chave"] = n0 - n1
    stats["removidas_por_duplicata"] = n1 - len(df)
    log.info(
        f"Removidas {n0 - n1:,} linhas com nulo em chave (data_base/uf/segmento) "
        f"e {n1 - len(df):,} duplicatas. Restam {len(df):,}."
    )

    # Garantir que só colunas necessárias sejam retidas
    colunas_presentes = [c for c in DB_COLS if c in df.columns]
    out = df[colunas_presentes]

    # Amostra da versao TRATADA (as mesmas linhas que sobreviveram)
    out.loc[out.index.intersection(amostra_idx)].to_csv(
        DOCS_DIR / "amostra_tratada.csv", sep=";", index=False, encoding="utf-8-sig"
    )

    stats["linhas_finais"] = len(out)
    return out.reset_index(drop=True)


# Carga no PostgreSQL

def load(df: pd.DataFrame) -> int:
    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        log.error("psycopg2 não instalado. Execute: pip install psycopg2-binary")
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        log.error("Variável DATABASE_URL não definida. Configure o arquivo .env.")
        sys.exit(1)

    log.info("Conectando ao PostgreSQL ...")
    # A URI do Aiven ja traz sslmode=require; so forcamos se nao estiver na URL
    kwargs = {} if "sslmode=" in db_url else {"sslmode": "require"}
    conn = psycopg2.connect(db_url, **kwargs)
    cur = conn.cursor()

    # Fonte unica do esquema: sql/schema.sql
    cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    cur.execute("TRUNCATE TABLE fato_microcredito RESTART IDENTITY;")
    log.info("Esquema aplicado e tabela truncada para recarga limpa.")

    cols = [c for c in DB_COLS if c in df.columns]

    def _safe(v):
        if pd.isna(v):
            return None
        # converte tipos numpy/pandas para tipos nativos do Python
        if hasattr(v, "item"):
            return v.item()
        return v

    records = [tuple(_safe(v) for v in row) for row in df[cols].itertuples(index=False)]

    sql = f"INSERT INTO fato_microcredito ({', '.join(cols)}) VALUES %s"
    execute_values(cur, sql, records, page_size=2000)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM fato_microcredito")
    n_banco = cur.fetchone()[0]
    log.info(f"{len(records):,} linhas enviadas; {n_banco:,} linhas confirmadas no banco.")
    cur.close()
    conn.close()
    return n_banco


# Ponto de entrada

def main() -> None:
    load_db = "--load-db" in sys.argv

    zip_files = sorted(ROOT_DIR.glob("scrdata_*.zip"))
    if not zip_files:
        log.error(f"Nenhum arquivo scrdata_*.zip encontrado em {ROOT_DIR}")
        sys.exit(1)
    log.info(f"Encontrados {len(zip_files)} ZIPs: {[z.name for z in zip_files]}")

    stats: dict = {
        "executado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arquivos_origem": [
            {"arquivo": z.name, "tamanho_bytes": z.stat().st_size, "sha256": _sha256(z)}
            for z in zip_files
        ],
    }

    raw, por_csv = extract(zip_files)
    stats["por_csv"] = por_csv
    stats["linhas_csv_total"] = sum(r["linhas_csv"] for r in por_csv)

    treated = transform(raw, stats)

    treated.to_parquet(OUTPUT_PARQUET, index=False, compression="snappy")
    tamanho_mb = OUTPUT_PARQUET.stat().st_size / 1e6
    stats["parquet"] = {"arquivo": OUTPUT_PARQUET.name, "tamanho_mb": round(tamanho_mb, 1)}
    log.info(f"Parquet salvo em {OUTPUT_PARQUET} ({tamanho_mb:.1f} MB)")

    if load_db:
        stats["linhas_no_banco"] = load(treated)
    else:
        log.info("Carga no banco ignorada. Para carregar, rode: python etl_scr.py --load-db")

    (DOCS_DIR / "relatorio_etl.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info(f"Relatorio salvo em {DOCS_DIR / 'relatorio_etl.json'}")


if __name__ == "__main__":
    main()
