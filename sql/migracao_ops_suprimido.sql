-- Migracao SEM recarregar o ETL: converte -1 em NULL e registra a flag.
-- Alternativa recomendada: rodar `python etl_scr.py --load-db`.

BEGIN;

ALTER TABLE fato_microcredito
    ADD COLUMN IF NOT EXISTS ops_suprimido BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE fato_microcredito
SET ops_suprimido = TRUE,
    numero_de_operacoes = NULL
WHERE numero_de_operacoes < 0;

COMMIT;

-- Rode FORA de transacao (o VACUUM nao funciona dentro de BEGIN/COMMIT).
-- Importante no Free Tier: o UPDATE deixa linhas mortas que ocupam espaco ate o VACUUM.
VACUUM (ANALYZE) fato_microcredito;

-- Depois, execute sql/schema.sql para criar o indice e a constraint de nao-negatividade.
