CREATE OR REPLACE FUNCTION atualiza_custo_m2()
RETURNS TRIGGER AS $$
BEGIN
    NEW.custo_m2 = CASE 
        WHEN NEW.area_m2 > 0 THEN ROUND(NEW.preco::NUMERIC / NEW.area_m2, 2)
        ELSE NULL
    END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION calcular_faixa_area()
RETURNS TRIGGER AS $$
BEGIN
    NEW.faixa_area = CASE
        WHEN NEW.area_m2 IS NULL THEN NULL
        WHEN NEW.area_m2 <= 50 THEN 'Até 50m²'
        WHEN NEW.area_m2 <= 100 THEN '51-100m²'
        WHEN NEW.area_m2 <= 150 THEN '101-150m²'
        WHEN NEW.area_m2 <= 200 THEN '151-200m²'
        ELSE 'Acima de 200m²'
    END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
