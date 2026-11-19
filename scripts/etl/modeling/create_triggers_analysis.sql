DROP TRIGGER IF EXISTS trigger_atualiza_custo_m2 ON imovel;
CREATE TRIGGER trigger_atualiza_custo_m2
BEFORE INSERT OR UPDATE ON imovel
FOR EACH ROW
EXECUTE FUNCTION atualiza_custo_m2();

DROP TRIGGER IF EXISTS trigger_calcular_faixa_area ON imovel;
CREATE TRIGGER trigger_calcular_faixa_area
BEFORE INSERT OR UPDATE ON imovel
FOR EACH ROW
EXECUTE FUNCTION calcular_faixa_area();