# Big Data & Analytics — Acesso a Microcrédito e Inclusão Financeira Regional

**Disciplina:** Big Data e Analytics  
**Tema 05:** Acesso a Microcrédito e Inclusão Financeira Regional  
**Fonte:** SCR.data — Sistema de Informações de Crédito do Banco Central do Brasil  
**ODS:** 5 (Igualdade de Gênero) · 8 (Trabalho Decente) · 10 (Redução das Desigualdades)

---

## Arquitetura da Solução

```
┌─────────────────────────────────┐
│  Fonte: BCB — SCR.data          │
│  scrdata_YYYY.zip (2021–2026)   │
│  CSV mensal · Latin-1 · ; sep   │
└──────────────┬──────────────────┘
               │ submodalidade == "Microcrédito"
               ▼
┌─────────────────────────────────┐
│  ETL — etl/etl_scr.py          │
│  · Extração dos ZIPs em memória │
│  · Filtro e limpeza (Pandas)    │
│  · Conversão de tipos           │
│  · Saída: microcredito_tratado  │
│    .parquet (Snappy)            │
└──────────────┬──────────────────┘
               │ psycopg2 + SSL
               ▼
┌─────────────────────────────────┐
│  PostgreSQL — Aiven Free Tier   │
│  Tabela: fato_microcredito      │
│  Provisionado via Terraform     │
└──────────────┬──────────────────┘
               │ (Marco 3)
               ▼
┌─────────────────────────────────┐
│  Dashboard — Streamlit Cloud    │
│  (a implementar no Marco 3)     │
└─────────────────────────────────┘
```

---

## 1. Dados Utilizados

| Item | Detalhe |
|------|---------|
| **Fonte** | Banco Central do Brasil — [SCR.data](https://www.bcb.gov.br/estabilidadefinanceira/scrdata) |
| **Formato de origem** | CSV mensal compactado em ZIP (`scrdata_AAAA.zip`) |
| **Encoding** | Latin-1 · Separador `;` |
| **Período** | Janeiro/2021 a Agosto/2026 (6 arquivos ZIP, ~12 CSVs cada) |
| **Granularidade** | Agregado por UF × Segmento × Porte × Modalidade × Mês |
| **Filtro aplicado** | `submodalidade == "Microcrédito"` |
| **Volume bruto estimado** | ~280 mil linhas/CSV × 12 × 6 anos ≈ 20 M linhas totais |
| **Volume após filtro** | ~150–300 mil linhas (estimativa; microcrédito é nicho pequeno) |

### Análise dos 5 V's

| V | Avaliação |
|---|-----------|
| **Volume** | Arquivos ZIP somam ~950 MB. Após filtro microcrédito o dataset cabe em 1 GB do Aiven Free Tier. |
| **Variedade** | Dados estruturados (CSV tabular). Colunas categóricas (UF, segmento, porte) + numéricas (carteiras, inadimplência). |
| **Velocidade** | Batch mensal publicado pelo BCB. Pipeline reproduzível via script local + GitHub Actions (futuro). |
| **Veracidade** | Fonte oficial regulatória. ETL remove nulos em chaves obrigatórias e elimina duplicatas. |
| **Valor** | Permite cruzar acesso ao microcrédito por região/porte/segmento — revelando desigualdades de inclusão financeira. |

### Tipos de Dados

- **Estruturados:** tabelas CSV com esquema fixo — 24 colunas definidas pelo BCB
- **Semi-estruturados:** metadados dos ZIPs (nomes de arquivos com data implícita)
- **Não estruturados:** ausentes nesta base

---

## 2. Tratamento Realizado

### Problemas identificados

| Problema | Decisão |
|----------|---------|
| Encoding Latin-1 | Leitura explícita com `encoding="latin-1"` |
| BOM (`﻿`) no cabeçalho | Strip + `lstrip("﻿")` no nome das colunas |
| Valores monetários como string (`"255.934,78"`) | Remove ponto de milhar → troca vírgula por ponto → `float` |
| `numero_de_operacoes` como string | `pd.to_numeric` → `Int64` (suporta `NaN`) |
| Linhas com UF, segmento ou data nulos | Descarte (`dropna` em chaves obrigatórias) |
| Duplicatas | `drop_duplicates()` |

### Transformações realizadas

1. **Filtro:** `submodalidade == "Microcrédito"` — reduz volume em ~95 %
2. **Normalização de colunas:** `strip().lower()` — elimina variações de espaço/capitalização
3. **Conversão de datas:** `data_base` → `datetime64` (era string `"YYYY-MM-DD"`)
4. **Conversão monetária:** 13 colunas de valores → `float64` (NUMERIC 18,2 no banco)
5. **Saída compactada:** Parquet com Snappy (~8× menor que CSV)

### Justificativas

- Parquet escolhido para saída intermediária por performance de leitura e compressão sem perda.
- Carga idempotente com `TRUNCATE + INSERT` garante reprocessamentos sem duplicar dados.
- Nenhum dado pessoal está presente (base é agregada por UF/segmento — LGPD não aplicável diretamente, mas segue boas práticas).

---

## 3. Modelagem do Banco de Dados

### Estratégia: Tabela Fato Plana (Flat Star)

Dado que o SCR.data já entrega dados **pré-agregados** (não registros individuais de operações), optou-se por uma única tabela fato desnormalizada. Isso simplifica as consultas analíticas e evita JOINs desnecessários dentro do limite de 1 GB.

### Tabela `fato_microcredito`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | SERIAL PK | Chave substituta |
| `data_base` | DATE | Competência da posição (último dia do mês) |
| `uf` | VARCHAR(2) | Unidade Federativa do tomador |
| `segmento` | VARCHAR(100) | Tipo de instituição (Banco, Fintech, Cooperativa…) |
| `cliente` | VARCHAR(20) | Pessoa Física (PF) ou Jurídica (PJ) |
| `cnae_ocupacao` | VARCHAR(200) | Setor econômico / ocupação do tomador |
| `porte` | VARCHAR(100) | Faixa de renda/porte (até 1 SM, micro, pequeno…) |
| `modalidade` | VARCHAR(100) | Modalidade de crédito (Empréstimos, Financiamentos…) |
| `submodalidade` | VARCHAR(100) | **Microcrédito** (filtrado) |
| `origem` | VARCHAR(100) | Destinação do crédito |
| `indexador` | VARCHAR(100) | Indexador da operação (Prefixado, IPCA…) |
| `numero_de_operacoes` | INTEGER | Quantidade de contratos ativos |
| `a_vencer_ate_90_dias` | NUMERIC(18,2) | Carteira a vencer em até 90 dias (R$) |
| `a_vencer_de_91_ate_360_dias` | NUMERIC(18,2) | Carteira a vencer 91–360 dias (R$) |
| `a_vencer_de_361_ate_1080_dias` | NUMERIC(18,2) | Carteira a vencer 361–1080 dias (R$) |
| `a_vencer_de_1081_ate_1800_dias` | NUMERIC(18,2) | Carteira a vencer 1081–1800 dias (R$) |
| `a_vencer_de_1801_ate_5400_dias` | NUMERIC(18,2) | Carteira a vencer 1801–5400 dias (R$) |
| `a_vencer_acima_de_5400_dias` | NUMERIC(18,2) | Carteira a vencer acima de 5400 dias (R$) |
| `carteira_a_vencer` | NUMERIC(18,2) | Total a vencer (R$) |
| `vencido_de_15_ate_90_dias` | NUMERIC(18,2) | Carteira vencida 15–90 dias (R$) |
| `vencido_acima_de_90_dias` | NUMERIC(18,2) | Carteira vencida > 90 dias (R$) |
| `carteira_vencida` | NUMERIC(18,2) | Total vencido (R$) |
| `carteira_ativa` | NUMERIC(18,2) | Carteira total ativa (R$) |
| `carteira_inadimplencia` | NUMERIC(18,2) | Carteira inadimplente (R$) |
| `ativo_problematico` | NUMERIC(18,2) | Ativo problemático (R$) |

**Justificativa da modelagem:** Uma única tabela fato flat é adequada pois (i) o SCR.data já é uma tabela analítica agregada; (ii) evita JOINs que penalizam performance no Free Tier; (iii) todas as dimensões (UF, segmento, porte) são de baixa cardinalidade e cabem inline.

---

## 4. Infraestrutura

| Item | Detalhe |
|------|---------|
| **Provedor de nuvem** | Aiven for PostgreSQL — Free Tier (Hobbyist, 1 GB) |
| **Região** | `google-southamerica-east1` (São Paulo) |
| **Versão** | PostgreSQL 16 |
| **IaC** | Terraform ≥ 1.5 · Provider `aiven/aiven ~> 4.0` |
| **Arquivos** | `terraform/main.tf`, `terraform/variables.tf`, `terraform/outputs.tf` |
| **Credenciais** | Token Aiven via variável Terraform (`sensitive = true`). URI do banco via `.env` local (nunca versionado). |

### Segurança

- Credenciais de banco (host, porta, senha) mantidas em `.env` local — **não versionadas** (`.gitignore` bloqueia `*.env`).
- Token da API Aiven passado via `secrets.tfvars` ou variável de ambiente `TF_VAR_aiven_api_token` — arquivo bloqueado no `.gitignore`.
- Repositório público não contém nenhuma credencial, chave ou token.

---

## 5. Execução (Guia Passo a Passo)

### Pré-requisitos

- Python ≥ 3.11
- Terraform ≥ 1.5
- Conta gratuita na [Aiven](https://aiven.io) com projeto criado
- ZIPs do SCR.data na raiz do projeto (`scrdata_2021.zip` … `scrdata_2026.zip`)

### Passo 1 — Instalar dependências Python

```bash
cd etl
pip install -r requirements.txt
```

### Passo 2 — Provisionar o banco com Terraform

```bash
cd terraform

# Crie o arquivo de variáveis (não commite este arquivo)
cat > secrets.tfvars <<EOF
aiven_api_token    = "SEU_TOKEN_AIVEN"
aiven_project_name = "NOME_DO_SEU_PROJETO"
EOF

terraform init
terraform plan -var-file="secrets.tfvars"
terraform apply -var-file="secrets.tfvars"

# Obter a URI de conexão
terraform output -raw service_uri
```

### Passo 3 — Configurar variável de ambiente

```bash
cd etl
cp .env.example .env
# Edite .env e cole a URI obtida no passo anterior
```

### Passo 4 — Executar o ETL

```bash
# Apenas tratar e salvar parquet (sem banco)
python etl_scr.py

# Tratar + carregar no PostgreSQL
python etl_scr.py --load-db
```

### Passo 5 — Verificar a carga

```sql
-- Conecte no banco e execute:
SELECT COUNT(*) FROM fato_microcredito;
SELECT data_base, uf, segmento, carteira_ativa
FROM fato_microcredito
ORDER BY data_base DESC
LIMIT 10;
```

---

## Estrutura do Repositório

```
big-data-microcredito/
├── etl/
│   ├── etl_scr.py             # Script ETL principal
│   ├── requirements.txt       # Dependências Python
│   └── .env.example           # Template de variáveis de ambiente
├── terraform/
│   ├── main.tf                # Recurso PostgreSQL Aiven
│   ├── variables.tf           # Variáveis de entrada
│   └── outputs.tf             # URI e conexão do banco
├── dashboard/                 # (Marco 3 — Streamlit)
├── .gitignore
└── README.md
```

---

## Decisões Técnicas Adotadas

| Decisão | Justificativa |
|---------|---------------|
| Filtrar por `submodalidade` (não `modalidade`) | A modalidade "Microcrédito" aparece somente na submodalidade; a modalidade principal é "Empréstimos" |
| Pandas para ETL (não PySpark) | Volume pós-filtro cabe em RAM (~300 mil linhas); Pandas é suficiente e sem overhead de cluster |
| Parquet + Snappy como formato intermediário | ~8× mais compacto que CSV; leitura mais rápida no Marco 3 (dashboard) |
| Tabela fato flat (sem dimensões separadas) | Dados já agregados pelo BCB; JOINs adicionariam complexidade sem ganho para o volume atual |
| Carga idempotente (TRUNCATE + INSERT) | Permite reprocessar o ETL a qualquer momento sem duplicar dados |
| PostgreSQL Aiven Free Tier | Atende o requisito da disciplina; 1 GB suficiente para o subconjunto microcrédito |
