-- Tabela para armazenar tipos de imóveis (ex.: apartamento, casa);
CREATE TABLE IF NOT EXISTS "tipo_imovel" (
  "id_tipo" SERIAL PRIMARY KEY,
  "tipo" VARCHAR(50) NOT NULL UNIQUE
);

-- Tabela para armazenar modos de imóveis (ex.: comprar, alugar);
CREATE TABLE IF NOT EXISTS "modo_imovel" (
  "id_modo" SERIAL PRIMARY KEY,
  "modo" VARCHAR(50) NOT NULL UNIQUE
);

-- Tabela para armazenar endereços de imóveis;
CREATE TABLE IF NOT EXISTS "endereco" (
  "id_endereco" SERIAL PRIMARY KEY,
  "endereco" VARCHAR(250),
  "bairro" VARCHAR(100),
  "cidade" VARCHAR(100) NOT NULL,
  "estado" VARCHAR(2) NOT NULL,
  "cep" VARCHAR(10),
  "rua" VARCHAR(100),
  "numero" INT
);

-- Tabela para armazenar dados de imobiliárias;
CREATE TABLE IF NOT EXISTS "imobiliaria" (
  "id_imobiliaria" SERIAL PRIMARY KEY,
  "id_endereco_imobiliaria" INTEGER NOT NULL,
  "nome_imobiliaria" VARCHAR(255) NOT NULL,
  "credencial_imobiliaria" VARCHAR(100),
  "quantidade_imovel" INTEGER DEFAULT 0,
  "data_cadastro_imobiliaria" DATE DEFAULT CURRENT_DATE,
  "telefone_imobiliaria" VARCHAR(20),
  "data_coleta_imobiliaria" DATE,
  FOREIGN KEY ("id_endereco_imobiliaria") REFERENCES "endereco" ("id_endereco")
);

-- Tabela para armazenar informações sobre imóveis;
CREATE TABLE IF NOT EXISTS "imovel" (
  "id_imovel" TEXT PRIMARY KEY,
  "id_imobiliaria" INTEGER NOT NULL,
  "id_endereco_imovel" INTEGER NOT NULL,
  "id_tipo_imovel" INTEGER NOT NULL,
  "id_modo_imovel" INTEGER NOT NULL,
  "titulo_imovel" VARCHAR(255) NOT NULL,
  "descricao_imovel" TEXT,
  "data_cadastro_imovel" DATE DEFAULT nULL,
  "data_atualizacao_imovel" DATE DEFAULT NULL,
  "imagens_imovel" TEXT[],
  "telefone_imovel" TEXT[],
  "preco" INT NOT NULL,
  "quantidade_quartos" INTEGER DEFAULT NULL,
  "quantidade_banheiros" INTEGER DEFAULT NULL,
  "quantidade_vagas" INTEGER DEFAULT NULL,
  "quantidade_suites" INTEGER DEFAULT NULL,
  "outros" TEXT,
  "area_m2" INTEGER,
  "custo_m2" NUMERIC,
  "faixa_area" VARCHAR(50),
  "data_coleta_imovel" DATE,
  "data_migracao" DATE,
  FOREIGN KEY ("id_imobiliaria") REFERENCES "imobiliaria" ("id_imobiliaria"),
  FOREIGN KEY ("id_endereco_imovel") REFERENCES "endereco" ("id_endereco"),
  FOREIGN KEY ("id_tipo_imovel") REFERENCES "tipo_imovel" ("id_tipo"),
  FOREIGN KEY ("id_modo_imovel") REFERENCES "modo_imovel" ("id_modo")
);

-- Histórico: uma observação de preço por imóvel e data de coleta;
CREATE TABLE IF NOT EXISTS "imovel_snapshot" (
  "id_imovel" TEXT NOT NULL,
  "data_coleta" DATE NOT NULL,
  "preco" INT NOT NULL,
  "condominio" INT,
  "iptu" INT,
  PRIMARY KEY ("id_imovel", "data_coleta"),
  FOREIGN KEY ("id_imovel") REFERENCES "imovel" ("id_imovel")
);

-- Staging dos snapshots (recriado pela migração; existe vazio para não quebrar o insert);
CREATE TABLE IF NOT EXISTS public._snapshots_imoveis (
  hash TEXT, snapshot_key TEXT, preco DOUBLE PRECISION,
  condominio DOUBLE PRECISION, iptu DOUBLE PRECISION, data_coleta TEXT,
  batch_id TEXT
);

-- Índices sugeridos para melhorar o desempenho;
CREATE INDEX IF NOT EXISTS idx_endereco_cidade ON "endereco" ("bairro");
CREATE INDEX IF NOT EXISTS idx_imobiliaria_nome ON "imobiliaria" ("nome_imobiliaria");
CREATE INDEX IF NOT EXISTS idx_imovel_preco ON "imovel" ("preco");
CREATE INDEX IF NOT EXISTS idx_snapshot_data ON "imovel_snapshot" ("data_coleta");

-- Endereço único: vários imóveis do mesmo endereço compartilham uma linha
-- (necessário para o upsert e para os joins por texto do insert);
CREATE UNIQUE INDEX IF NOT EXISTS ux_endereco_endereco ON "endereco" ("endereco");
