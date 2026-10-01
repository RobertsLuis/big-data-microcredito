# Big Data e Analytics: Acesso a Microcredito e Inclusao Financeira Regional

Disciplina: Big Data e Analytics
Tema 05: Acesso a Microcredito e Inclusao Financeira Regional
Fonte: SCR.data - Sistema de Informacoes de Credito do Banco Central do Brasil
ODS: 5 (Igualdade de Genero), 8 (Trabalho Decente), 10 (Reducao das Desigualdades)

## Arquitetura da solucao

```
+----------------------------------+
|  Fonte: BCB - SCR.data           |
|  scrdata_YYYY.zip (2021-2026)    |
|  CSV mensal, UTF-8, sep ;        |
+---------------+------------------+
                |  submodalidade == "Microcredito"
                v
+----------------------------------+
|  ETL - etl/etl_scr.py           |
|  - Extracao dos ZIPs em memoria  |
|  - Filtro e limpeza (Pandas)     |
|  - Conversao de tipos            |
|  - Saida: microcredito_tratado   |
|    .parquet (Snappy)             |
+---------------+------------------+
                |  psycopg2 + SSL
                v
+----------------------------------+
|  PostgreSQL - Aiven Free Tier    |
|  Tabela: fato_microcredito       |
|  Provisionado via Terraform      |
+---------------+------------------+
                |  (Marco 3)
                v
+----------------------------------+
|  Dashboard - Streamlit Cloud     |
|  (a implementar no Marco 3)      |
+----------------------------------+
```

## 1. Dados utilizados

| Item | Detalhe |
|------|---------|
| Fonte | Banco Central do Brasil - [SCR.data](https://www.bcb.gov.br/estabilidadefinanceira/scrdata) |
| Formato de origem | CSV mensal compactado em ZIP (`scrdata_AAAA.zip`) |
| Encoding | UTF-8 com BOM, separador `;` |
| Periodo | Janeiro/2021 a Julho/2026 (6 arquivos ZIP, ~12 CSVs cada) |
| Granularidade | Agregado por UF x Segmento x Porte x Modalidade x Mes |
| Filtro aplicado | `submodalidade == "Microcredito"` |
| Volume bruto estimado | ~280 mil linhas por CSV, cerca de 20 milhoes no total |
| Volume apos filtro | 598.002 linhas carregadas no banco |

### Analise dos 5 Vs

| V | Avaliacao |
|---|-----------|
| Volume | Os ZIPs somam cerca de 950 MB. Depois de filtrar so microcredito, o dataset cabe dentro do limite de 1 GB do Aiven Free Tier. |
| Variedade | Dados estruturados em CSV tabular, com colunas categoricas (UF, segmento, porte) e numericas (carteiras, inadimplencia). |
| Velocidade | O BCB publica a base mensalmente em lote. O pipeline pode ser agendado via GitHub Actions para rodar automaticamente. |
| Veracidade | Fonte oficial e regulatoria. O ETL remove nulos nas colunas obrigatorias e elimina duplicatas antes da carga. |
| Valor | Cruzando os dados por regiao, porte e segmento da instituicao, da pra identificar onde o acesso ao microcredito e mais restrito e para quem. |

### Tipos de dados

- Estruturados: tabelas CSV com esquema fixo, 24 colunas definidas pelo BCB
- Semi-estruturados: metadados dos ZIPs (nomes de arquivo carregam o mes de referencia)
- Nao estruturados: nao existem nesta base

## 2. Tratamento realizado

### Problemas identificados e decisoes tomadas

| Problema | Decisao |
|----------|---------|
| Encoding UTF-8 com BOM | Leitura com `encoding="utf-8-sig"`, que ja remove o BOM automaticamente |
| Valores monetarios como string (`"255.934,78"`) | Remove o ponto de milhar, troca virgula por ponto, converte para `float` |
| `numero_de_operacoes` como string | `pd.to_numeric` convertido para `Int64`, que aceita valores nulos |
| Linhas com UF, segmento ou data nulos | Descarte via `dropna` nas colunas que sao chave da analise |
| Duplicatas | Removidas com `drop_duplicates()` |

### Transformacoes aplicadas

1. Filtro: `submodalidade == "Microcredito"` reduz o volume em cerca de 95%
2. Normalizacao de colunas: `strip().lower()` elimina espacos e variacao de capitalização
3. Conversao de datas: `data_base` para `datetime64` (chegava como string `"YYYY-MM-DD"`)
4. Conversao monetaria: 13 colunas de valores para `float64` (salvas como NUMERIC 18,2 no banco)
5. Saida compactada: Parquet com Snappy, cerca de 8 vezes menor que o CSV original

### Por que essas escolhas

O Parquet foi escolhido para a saida intermediaria porque a leitura e mais rapida e a compressao nao perde dados. A carga no banco usa `TRUNCATE + INSERT`, o que garante que rodar o ETL mais de uma vez nao cria registros duplicados. A base do BCB e agregada por UF e segmento, sem dados de pessoas fisicas identificaveis, entao nao ha risco de LGPD nessa etapa.

## 3. Modelagem do banco de dados

O SCR.data ja chega pre-agregado, sem registros individuais de operacoes de credito. Por isso optamos por uma tabela fato unica e desnormalizada. Criar tabelas de dimensao separadas adicionaria complexidade sem nenhum ganho real, especialmente dentro do limite de 1 GB do Free Tier.

### Tabela `fato_microcredito`

| Coluna | Tipo | Descricao |
|--------|------|-----------|
| `id` | SERIAL PK | Chave substituta |
| `data_base` | DATE | Competencia da posicao (ultimo dia do mes) |
| `uf` | VARCHAR(2) | Unidade Federativa do tomador |
| `segmento` | VARCHAR(100) | Tipo de instituicao (Banco, Fintech, Cooperativa...) |
| `cliente` | VARCHAR(20) | Pessoa Fisica (PF) ou Juridica (PJ) |
| `cnae_ocupacao` | VARCHAR(200) | Setor economico ou ocupacao do tomador |
| `porte` | VARCHAR(100) | Faixa de renda ou porte (ate 1 SM, micro, pequeno...) |
| `modalidade` | VARCHAR(100) | Modalidade de credito (Emprestimos, Financiamentos...) |
| `submodalidade` | VARCHAR(100) | Microcredito (valor filtrado) |
| `origem` | VARCHAR(100) | Destinacao do credito |
| `indexador` | VARCHAR(100) | Indexador da operacao (Prefixado, IPCA...) |
| `numero_de_operacoes` | INTEGER | Quantidade de contratos ativos |
| `a_vencer_ate_90_dias` | NUMERIC(18,2) | Carteira a vencer em ate 90 dias (R$) |
| `a_vencer_de_91_ate_360_dias` | NUMERIC(18,2) | Carteira a vencer entre 91 e 360 dias (R$) |
| `a_vencer_de_361_ate_1080_dias` | NUMERIC(18,2) | Carteira a vencer entre 361 e 1080 dias (R$) |
| `a_vencer_de_1081_ate_1800_dias` | NUMERIC(18,2) | Carteira a vencer entre 1081 e 1800 dias (R$) |
| `a_vencer_de_1801_ate_5400_dias` | NUMERIC(18,2) | Carteira a vencer entre 1801 e 5400 dias (R$) |
| `a_vencer_acima_de_5400_dias` | NUMERIC(18,2) | Carteira a vencer acima de 5400 dias (R$) |
| `carteira_a_vencer` | NUMERIC(18,2) | Total a vencer (R$) |
| `vencido_de_15_ate_90_dias` | NUMERIC(18,2) | Carteira vencida entre 15 e 90 dias (R$) |
| `vencido_acima_de_90_dias` | NUMERIC(18,2) | Carteira vencida acima de 90 dias (R$) |
| `carteira_vencida` | NUMERIC(18,2) | Total vencido (R$) |
| `carteira_ativa` | NUMERIC(18,2) | Carteira total ativa (R$) |
| `carteira_inadimplencia` | NUMERIC(18,2) | Carteira inadimplente (R$) |
| `ativo_problematico` | NUMERIC(18,2) | Ativo problematico (R$) |

## 4. Infraestrutura

| Item | Detalhe |
|------|---------|
| Provedor | Aiven for PostgreSQL, plano Free Tier (Hobbyist, 1 GB) |
| Regiao | `google-southamerica-east1` (Sao Paulo) |
| Versao | PostgreSQL 16 |
| IaC | Terraform >= 1.5, provider `aiven/aiven ~> 4.0` |
| Arquivos | `terraform/main.tf`, `terraform/variables.tf`, `terraform/outputs.tf` |
| Credenciais | Token Aiven via variavel Terraform marcada como `sensitive`. URI do banco via `.env` local, nunca versionado. |

### Seguranca

As credenciais do banco (host, porta, senha) ficam so no `.env` local, que esta no `.gitignore`. O token da API Aiven e passado via `secrets.tfvars`, tambem bloqueado no `.gitignore`. O repositorio publico nao tem nenhuma senha, chave ou token.

## 5. Como rodar

### Pre-requisitos

- Python 3.11 ou superior
- Terraform 1.5 ou superior
- Conta gratuita na [Aiven](https://aiven.io) com um projeto criado
- ZIPs do SCR.data na raiz do projeto (`scrdata_2021.zip` ate `scrdata_2026.zip`)

### Passo 1: instalar as dependencias Python

```bash
cd etl
pip install -r requirements.txt
```

### Passo 2: provisionar o banco com Terraform

```bash
cd terraform

# Crie o arquivo de variaveis (nao commite este arquivo)
cat > secrets.tfvars <<EOF
aiven_api_token    = "SEU_TOKEN_AIVEN"
aiven_project_name = "NOME_DO_SEU_PROJETO"
EOF

terraform init
terraform plan -var-file="secrets.tfvars"
terraform apply -var-file="secrets.tfvars"

# Pegar a URI de conexao
terraform output -raw service_uri
```

### Passo 3: configurar o arquivo .env

```bash
cd etl
cp .env.example .env
# Abra o .env e cole a URI que o Terraform gerou
```

### Passo 4: rodar o ETL

```bash
# So tratar e salvar o parquet, sem subir pro banco
python etl_scr.py

# Tratar e carregar no PostgreSQL
python etl_scr.py --load-db
```

### Passo 5: confirmar a carga

```sql
SELECT COUNT(*) FROM fato_microcredito;
SELECT data_base, uf, segmento, carteira_ativa
FROM fato_microcredito
ORDER BY data_base DESC
LIMIT 10;
```

## Estrutura do repositorio

```
big-data-microcredito/
├── etl/
│   ├── etl_scr.py             # Script ETL principal
│   ├── requirements.txt       # Dependencias Python
│   └── .env.example           # Template das variaveis de ambiente
├── terraform/
│   ├── main.tf                # Recurso PostgreSQL Aiven
│   ├── variables.tf           # Variaveis de entrada
│   └── outputs.tf             # URI e dados de conexao do banco
├── dashboard/                 # (Marco 3 - Streamlit)
├── .gitignore
└── README.md
```

## Decisoes tecnicas

| Decisao | Motivo |
|---------|--------|
| Filtrar por `submodalidade` e nao por `modalidade` | O microcredito aparece so na submodalidade; na modalidade o campo e "Emprestimos" |
| Pandas no lugar de PySpark | Com 598 mil linhas pos-filtro, o Pandas resolve sem precisar de cluster |
| Parquet com Snappy como saida intermediaria | Ocupa cerca de 8 vezes menos que CSV e carrega mais rapido no dashboard |
| Tabela fato unica sem dimensoes separadas | Os dados ja chegam agregados do BCB; tabelas de dimensao nao trariam ganho nenhum aqui |
| Carga com TRUNCATE antes do INSERT | Permite reprocessar o ETL quantas vezes precisar sem duplicar linhas |
| PostgreSQL no Aiven Free Tier | Atende o requisito da disciplina e 1 GB e suficiente para o volume de microcredito |
