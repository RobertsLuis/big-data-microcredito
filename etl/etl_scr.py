"""
ETL - SCR.data (Banco Central) - Microcredito
Filtra submodalidade == 'Microcrédito', converte tipos, salva parquet e carrega no PostgreSQL Aiven.

Uso:
    python etl_scr.py              # trata e salva parquet (sem banco)
    python etl_scr.py --load-db    # trata, salva parquet e carrega no banco
"""

import os
import io
import sys
import zipfile
import logging
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
ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PARQUET = Path(__file__).resolve().parent / "microcredito_tratado.parquet"

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

# Colunas que vao para o banco (mesma ordem do CREATE TABLE)
DB_COLS = [
    "data_base", "uf", "segmento", "cliente", "cnae_ocupacao", "porte",
    "modalidade", "submodalidade", "origem", "indexador",
    "numero_de_operacoes", *MONETARY_COLS,
]


# Leitura

def _read_csv_from_zip(zf: zipfile.ZipFile, name: str) -> pd.DataFrame:
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
    return df[df["submodalidade"] == "Microcrédito"].copy()


def extract(zip_files: list[Path]) -> pd.DataFrame:
    frames = []
    for zp in zip_files:
        log.info(f"Lendo {zp.name} ...")
        with zipfile.ZipFile(zp) as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            for name in sorted(csv_names):
                chunk = _read_csv_from_zip(zf, name)
                log.info(f"  {name}: {len(chunk):,} linhas de microcrédito")
                frames.append(chunk)
    if not frames:
        raise RuntimeError("Nenhum dado encontrado. Verifique os ZIPs no diretorio raiz.")
    return pd.concat(frames, ignore_index=True)


# Transformacao

def transform(df: pd.DataFrame) -> pd.DataFrame:
    log.info(f"Transformando {len(df):,} linhas ...")

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

    # Inteiro
    df["numero_de_operacoes"] = pd.to_numeric(
        df["numero_de_operacoes"], errors="coerce"
    ).astype("Int64")

    # Remover nulos em chaves obrigatórias
    antes = len(df)
    df.dropna(subset=["data_base", "uf", "segmento"], inplace=True)
    df.drop_duplicates(inplace=True)
    log.info(f"Removidas {antes - len(df):,} linhas nulas/duplicadas. Restam {len(df):,}.")

    # Garantir que só colunas necessárias sejam retidas
    colunas_presentes = [c for c in DB_COLS if c in df.columns]
    return df[colunas_presentes].reset_index(drop=True)


# Carga no PostgreSQL

def _create_table(cur) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fato_microcredito (
            id                          SERIAL PRIMARY KEY,
            data_base                   DATE          NOT NULL,
            uf                          VARCHAR(2),
            segmento                    VARCHAR(100),
            cliente                     VARCHAR(20),
            cnae_ocupacao               VARCHAR(200),
            porte                       VARCHAR(100),
            modalidade                  VARCHAR(100),
            submodalidade               VARCHAR(100),
            origem                      VARCHAR(100),
            indexador                   VARCHAR(100),
            numero_de_operacoes         INTEGER,
            a_vencer_ate_90_dias        NUMERIC(18,2),
            a_vencer_de_91_ate_360_dias NUMERIC(18,2),
            a_vencer_de_361_ate_1080_dias NUMERIC(18,2),
            a_vencer_de_1081_ate_1800_dias NUMERIC(18,2),
            a_vencer_de_1801_ate_5400_dias NUMERIC(18,2),
            a_vencer_acima_de_5400_dias NUMERIC(18,2),
            carteira_a_vencer           NUMERIC(18,2),
            vencido_de_15_ate_90_dias   NUMERIC(18,2),
            vencido_acima_de_90_dias    NUMERIC(18,2),
            carteira_vencida            NUMERIC(18,2),
            carteira_ativa              NUMERIC(18,2),
            carteira_inadimplencia      NUMERIC(18,2),
            ativo_problematico          NUMERIC(18,2)
        );
    """)


def load(df: pd.DataFrame) -> None:
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

    log.info("Conectando ao PostgreSQL Aiven ...")
    conn = psycopg2.connect(db_url, sslmode="require")
    cur = conn.cursor()

    _create_table(cur)
    cur.execute("TRUNCATE TABLE fato_microcredito RESTART IDENTITY;")
    log.info("Tabela truncada para recarga limpa.")

    cols = [c for c in DB_COLS if c in df.columns]

    def _safe(v):
        if pd.isna(v):
            return None
        # converte pandas Int64 para int nativo do Python
        if hasattr(v, "item"):
            return v.item()
        return v

    records = [tuple(_safe(v) for v in row) for row in df[cols].itertuples(index=False)]

    sql = f"INSERT INTO fato_microcredito ({', '.join(cols)}) VALUES %s"
    execute_values(cur, sql, records, page_size=2000)
    conn.commit()
    log.info(f"{len(records):,} linhas carregadas com sucesso.")
    cur.close()
    conn.close()


# Ponto de entrada

def main() -> None:
    load_db = "--load-db" in sys.argv

    zip_files = sorted(ROOT_DIR.glob("scrdata_*.zip"))
    if not zip_files:
        log.error(f"Nenhum arquivo scrdata_*.zip encontrado em {ROOT_DIR}")
        sys.exit(1)
    log.info(f"Encontrados {len(zip_files)} ZIPs: {[z.name for z in zip_files]}")

    raw = extract(zip_files)
    treated = transform(raw)

    OUTPUT_PARQUET.parent.mkdir(exist_ok=True)
    treated.to_parquet(OUTPUT_PARQUET, index=False, compression="snappy")
    log.info(f"Parquet salvo em {OUTPUT_PARQUET} ({OUTPUT_PARQUET.stat().st_size / 1e6:.1f} MB)")

    if load_db:
        load(treated)
    else:
        log.info("Pule a carga no banco. Para carregar, rode: python etl_scr.py --load-db")


if __name__ == "__main__":
    main()
