-- Insere valores na tabela dimensão "tipo_imovel";
INSERT INTO public."tipo_imovel"(tipo)
VALUES
    ('teste'),
  	('casas'),
	('apartamentos'),
	('quitinetes'),
	('casas-de-condominio'),
	('cobertura'),
	('flat'),
	('float')
ON CONFLICT (tipo) DO NOTHING;

-- Insere valores na tabela dimensão "modo_imovel";
INSERT INTO public."modo_imovel"(modo)
VALUES
    ('teste'),
  	('venda'),
	('aluguel')
ON CONFLICT (modo) DO NOTHING;

-- Inclui tipos e modos que apareceram na coleta e não estão na lista fixa
-- (evita que o INNER JOIN da tabela fato descarte imóveis em silêncio);
INSERT INTO public."tipo_imovel"(tipo)
SELECT DISTINCT LOWER(tipo_imovel)
FROM public._treat_imoveis
WHERE tipo_imovel IS NOT NULL
ON CONFLICT (tipo) DO NOTHING;

INSERT INTO public."modo_imovel"(modo)
SELECT DISTINCT LOWER(modo_imovel)
FROM public._treat_imoveis
WHERE modo_imovel IS NOT NULL
ON CONFLICT (modo) DO NOTHING;

-- Insere valores na tabela dimensão "endereco";
INSERT INTO public."endereco" (
	endereco,
	bairro,
    cidade,
    estado,
    rua,
	numero
)
SELECT 
    endereco_completo,
	bairro,
	'Uberlândia',
	'MG',
	COALESCE(rua, 'Não Definido'),
	COALESCE(numero::integer, 0)
FROM public._treat_imoveis
UNION ALL
SELECT 
    endereco_completo,
	bairro,
	'Uberlândia',
	'MG',
	COALESCE(rua, 'Não Definido'),
	COALESCE(numero::integer, 0)
FROM public._treat_imobiliarias
ON CONFLICT (endereco) DO NOTHING;

-- Insere valores na tabela dimensão "imobiliaria";
INSERT INTO public.imobiliaria(
    id_imobiliaria,
    id_endereco_imobiliaria,
    nome_imobiliaria,
    credencial_imobiliaria,
    quantidade_imovel,
    data_cadastro_imobiliaria,
    telefone_imobiliaria,
    data_coleta_imobiliaria
)
SELECT 
    id_imobiliaria,
    B.id_endereco,
    nome_imobiliaria,
    COALESCE(credencial_imobiliaria, 'Não informado'),
    CAST (quantidade_imovel AS INTEGER),
    TO_DATE(data_cadastro, 'DD-MM-YYYY'),
    COALESCE(telefone, 'Não informado'),
    TO_DATE(data_coleta, 'DD-MM-YYYY')
FROM public._treat_imobiliarias A
INNER JOIN public.endereco B
    ON A.endereco_completo = B.endereco
ON CONFLICT (id_imobiliaria) DO UPDATE SET
    nome_imobiliaria = EXCLUDED.nome_imobiliaria,
    quantidade_imovel = EXCLUDED.quantidade_imovel,
    data_coleta_imobiliaria = EXCLUDED.data_coleta_imobiliaria;
	
-- Insere valores na tabela fato "imovel";
INSERT INTO public.imovel(
    id_imovel,
    id_imobiliaria,
    id_endereco_imovel,
    id_tipo_imovel,
    id_modo_imovel,
    titulo_imovel,
    descricao_imovel,
    data_cadastro_imovel,
    data_atualizacao_imovel,
    imagens_imovel,
    telefone_imovel,
    preco,
    quantidade_quartos,
    quantidade_banheiros,
    quantidade_vagas,
    quantidade_suites,
    outros,
    area_m2,
    custo_m2,
    faixa_area,
    data_coleta_imovel
)
SELECT 
    hash,
    B.id_imobiliaria,
    C.id_endereco,
    D.id_tipo,
    E.id_modo,
    titulo_anuncio,
    descricao,
    TO_DATE(data_cadastro, 'DD-MM-YYYY'),
    TO_DATE(data_atualizacao, 'DD-MM-YYYY'),
    string_to_array(
        REPLACE(
            REPLACE(imagens, '{', ''),
            '}', ''
        ), ','
    ) AS imagens_imovel,
    string_to_array(
        REPLACE(
            REPLACE(A.telefone, '{', ''),
            '}', ''
        ), ','
    ) AS telefone_imovel,
    preco::INTEGER,
    quartos::INTEGER,
    banheiro::INTEGER,
    vagas::INTEGER,
    suite::INTEGER,
    REPLACE(
        REPLACE(
            REPLACE(outros, '"', ''),
            '{', ''
        ),
        '}', ''
    ) AS outros,
    area::INTEGER AS area_m2,
    CASE 
        WHEN area::INTEGER > 0 THEN preco::NUMERIC / area::INTEGER
        ELSE NULL
    END AS custo_m2,
    CASE
        WHEN area::INTEGER <= 50 THEN 'Até 50m²'
        WHEN area::INTEGER BETWEEN 51 AND 100 THEN '51-100m²'
        WHEN area::INTEGER BETWEEN 101 AND 150 THEN '101-150m²'
        WHEN area::INTEGER BETWEEN 151 AND 200 THEN '151-200m²'
        ELSE 'Acima de 200m²'
    END AS faixa_area,
    TO_DATE(data_coleta_imovel, 'DD-MM-YYYY')
FROM 
    public._treat_imoveis A
INNER JOIN 
    public.imobiliaria B ON A.id_imobiliaria = B.id_imobiliaria
INNER JOIN 
    public.endereco C ON A.endereco_completo = C.endereco
INNER JOIN 
    public.tipo_imovel D ON LOWER(A.tipo_imovel) = LOWER(D.tipo)
INNER JOIN 
    public.modo_imovel E ON LOWER(A.modo_imovel) = LOWER(E.modo)
ON CONFLICT (id_imovel) DO UPDATE SET
    descricao_imovel = EXCLUDED.descricao_imovel,
    imagens_imovel = EXCLUDED.imagens_imovel,
    data_atualizacao_imovel = EXCLUDED.data_atualizacao_imovel
WHERE (imovel.descricao_imovel, imovel.data_atualizacao_imovel)
    IS DISTINCT FROM
    (EXCLUDED.descricao_imovel, EXCLUDED.data_atualizacao_imovel);

-- Histórico de preço: uma linha por imóvel e data de coleta;
INSERT INTO public.imovel_snapshot (
    id_imovel, data_coleta, preco, condominio, iptu
)
SELECT
    S.hash,
    TO_DATE(S.data_coleta, 'DD/MM/YYYY'),
    S.preco::INTEGER,
    S.condominio::INTEGER,
    S.iptu::INTEGER
FROM public._snapshots_imoveis S
INNER JOIN public.imovel I ON I.id_imovel = S.hash
WHERE S.preco IS NOT NULL
ON CONFLICT (id_imovel, data_coleta) DO UPDATE SET
    preco = EXCLUDED.preco,
    condominio = EXCLUDED.condominio,
    iptu = EXCLUDED.iptu;

-- O preço atual do imóvel é o do snapshot mais recente (fonte da verdade);
UPDATE public.imovel I
SET preco = L.preco,
    data_coleta_imovel = L.data_coleta
FROM (
    SELECT DISTINCT ON (id_imovel) id_imovel, preco, data_coleta
    FROM public.imovel_snapshot
    ORDER BY id_imovel, data_coleta DESC
) L
WHERE I.id_imovel = L.id_imovel
  AND (I.preco IS DISTINCT FROM L.preco
       OR I.data_coleta_imovel IS DISTINCT FROM L.data_coleta);
