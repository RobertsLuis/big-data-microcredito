
CREATE TABLE IF NOT EXISTS fato_microcredito (
    id                              SERIAL PRIMARY KEY,
    data_base                       DATE           NOT NULL,
    uf                              VARCHAR(2),
    segmento                        VARCHAR(100),
    cliente                         VARCHAR(20),
    cnae_ocupacao                   VARCHAR(200),
    porte                           VARCHAR(100),
    modalidade                      VARCHAR(100),
    submodalidade                   VARCHAR(100),
    origem                          VARCHAR(100),
    indexador                       VARCHAR(100),
    numero_de_operacoes             INTEGER,
    ops_suprimido                   BOOLEAN        NOT NULL DEFAULT FALSE,
    a_vencer_ate_90_dias            NUMERIC(18,2),
    a_vencer_de_91_ate_360_dias     NUMERIC(18,2),
    a_vencer_de_361_ate_1080_dias   NUMERIC(18,2),
    a_vencer_de_1081_ate_1800_dias  NUMERIC(18,2),
    a_vencer_de_1801_ate_5400_dias  NUMERIC(18,2),
    a_vencer_acima_de_5400_dias     NUMERIC(18,2),
    carteira_a_vencer               NUMERIC(18,2),
    vencido_de_15_ate_90_dias       NUMERIC(18,2),
    vencido_acima_de_90_dias        NUMERIC(18,2),
    carteira_vencida                NUMERIC(18,2),
    carteira_ativa                  NUMERIC(18,2),
    carteira_inadimplencia          NUMERIC(18,2),
    ativo_problematico              NUMERIC(18,2)
);

ALTER TABLE fato_microcredito
    ADD COLUMN IF NOT EXISTS ops_suprimido BOOLEAN NOT NULL DEFAULT FALSE;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ops_nao_negativo') THEN
        ALTER TABLE fato_microcredito
            ADD CONSTRAINT ck_ops_nao_negativo
            CHECK (numero_de_operacoes IS NULL OR numero_de_operacoes >= 0) NOT VALID;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_fato_data_uf ON fato_microcredito (data_base, uf);

COMMENT ON TABLE  fato_microcredito IS 'SCR.data (BCB): microcredito agregado por UF x segmento x porte x modalidade x mes';
COMMENT ON COLUMN fato_microcredito.data_base IS 'Data-base da posicao (saldos no fim do mes). Medidas de carteira sao ESTOQUE: nao somar entre meses';
COMMENT ON COLUMN fato_microcredito.numero_de_operacoes IS 'Contagem de operacoes. NULL quando o BCB informa valor negativo (-1)';
COMMENT ON COLUMN fato_microcredito.ops_suprimido IS 'TRUE quando o valor original era negativo (-1), interpretado pela equipe como contagem suprimida';
COMMENT ON COLUMN fato_microcredito.carteira_ativa IS 'Carteira a vencer + carteira vencida na data-base (R$) - Metodologia V2, item w';
