CREATE OR REPLACE VIEW distribuicao_tipo AS
SELECT
    tipo,
    COUNT(*) AS quantidade
FROM public.imovel A
INNER JOIN public.tipo_imovel B ON A.id_tipo_imovel = B.id_tipo
GROUP BY tipo;

CREATE OR REPLACE VIEW distribuicao_modo AS
SELECT
	modo,
	COUNT(*) 
FROM public.imovel A
	INNER JOIN public.modo_imovel B ON A.id_modo_imovel = B.id_modo
GROUP BY  modo;

CREATE OR REPLACE VIEW distribuicao_bairro AS
SELECT
	bairro,
	COUNT(*)
FROM public.imovel I
INNER JOIN public.endereco A ON A.id_endereco = I.id_endereco_imovel
GROUP BY bairro;

CREATE OR REPLACE VIEW distribuicao_bairro_modo AS
SELECT 
	bairro,
	modo,
	COUNT(*)
FROM public.endereco A
INNER JOIN public.imovel B ON B.id_endereco_imovel = A.id_endereco
INNER JOIN public.modo_imovel C ON C.id_modo = B.id_modo_imovel
GROUP BY bairro, modo
ORDER BY bairro;

CREATE OR REPLACE VIEW media_preco_bairro_modo_tipo AS
SELECT 
	bairro,
	tipo,
	modo,
	ROUND(AVG(B.preco),2) AS media_preco
FROM public.endereco A
INNER JOIN public.imovel B ON B.id_endereco_imovel = A.id_endereco
INNER JOIN public.modo_imovel C ON C.id_modo = B.id_modo_imovel
INNER JOIN public.tipo_imovel D ON D.id_tipo = B.id_tipo_imovel
GROUP BY bairro, modo, tipo
ORDER BY bairro;

CREATE OR REPLACE VIEW media_preco_modo_tipo AS
SELECT 
	tipo,
	modo,
	ROUND(AVG(B.preco),2) AS media_preco
FROM public.imovel B
INNER JOIN public.modo_imovel C ON C.id_modo = B.id_modo_imovel
INNER JOIN public.tipo_imovel D ON D.id_tipo = B.id_tipo_imovel
GROUP BY modo, tipo
ORDER BY MODO;

CREATE OR REPLACE VIEW dispersao_preco_quartos_area AS
SELECT 
    id_imovel,
    preco,
    quantidade_quartos,
    area_m2
FROM 
    imovel
WHERE 
    preco IS NOT NULL
    AND (quantidade_quartos IS NOT NULL OR area_m2 IS NOT NULL)
	AND id_imovel != '1'
	AND id_imobiliaria != '1'
	AND id_endereco_imovel != '1'
	AND id_tipo_imovel != '1'
	AND id_modo_imovel != '1';

CREATE OR REPLACE VIEW dispersao_faixa_area_modo_tipo AS
SELECT 
    faixa_area,
	modo,
	tipo,
    COUNT(*)
FROM imovel A
INNER JOIN public.modo_imovel B
	ON A.id_modo_imovel = B.id_modo
INNER JOIN public.tipo_imovel C
	ON A.id_tipo_imovel = C.id_tipo
WHERE 
    preco IS NOT NULL
    AND (quantidade_quartos IS NOT NULL OR area_m2 IS NOT NULL)
	AND id_imovel != '1'
	AND id_imobiliaria != '1'
	AND id_endereco_imovel != '1'
	AND id_tipo_imovel != '1'
	AND id_modo_imovel != '1'
GROUP BY faixa_area, modo, tipo
ORDER BY 
    CASE faixa_area
        WHEN 'Até 50m²' THEN 1
        WHEN '51-100m²' THEN 2
        WHEN '101-150m²' THEN 3
        WHEN '151-200m²' THEN 4
        WHEN 'Acima de 200m²' THEN 5
        ELSE 6 -- Para valores fora das categorias especificadas
    END;


-- Ciclo de vida do anúncio: primeira/última coleta, tempo no mercado e variação de preço.
-- "visto_na_ultima_coleta" = apareceu na coleta mais recente (não significa que
-- foi removido se ficou de fora: a coleta pode cobrir só parte das páginas);
CREATE OR REPLACE VIEW imovel_ciclo_vida AS
WITH obs AS (
    SELECT
        id_imovel,
        data_coleta,
        preco,
        LAG(preco) OVER (PARTITION BY id_imovel ORDER BY data_coleta) AS preco_anterior
    FROM public.imovel_snapshot
),
resumo AS (
    SELECT
        id_imovel,
        MIN(data_coleta) AS primeira_coleta,
        MAX(data_coleta) AS ultima_coleta,
        COUNT(*) AS coletas,
        (ARRAY_AGG(preco ORDER BY data_coleta ASC))[1] AS preco_inicial,
        (ARRAY_AGG(preco ORDER BY data_coleta DESC))[1] AS preco_atual,
        COUNT(*) FILTER (
            WHERE preco_anterior IS NOT NULL AND preco_anterior <> preco
        ) AS mudancas_preco
    FROM obs
    GROUP BY id_imovel
)
SELECT
    I.id_imovel,
    T.tipo,
    M.modo,
    E.bairro,
    I.data_cadastro_imovel,
    R.primeira_coleta,
    R.ultima_coleta,
    R.coletas,
    (R.ultima_coleta - I.data_cadastro_imovel) AS dias_no_mercado,
    R.preco_inicial,
    R.preco_atual,
    ROUND(100.0 * (R.preco_atual - R.preco_inicial) / NULLIF(R.preco_inicial, 0), 1) AS variacao_pct,
    R.mudancas_preco,
    (R.ultima_coleta = (SELECT MAX(data_coleta) FROM public.imovel_snapshot)) AS visto_na_ultima_coleta
FROM resumo R
INNER JOIN public.imovel I ON I.id_imovel = R.id_imovel
INNER JOIN public.tipo_imovel T ON T.id_tipo = I.id_tipo_imovel
INNER JOIN public.modo_imovel M ON M.id_modo = I.id_modo_imovel
INNER JOIN public.endereco E ON E.id_endereco = I.id_endereco_imovel;
