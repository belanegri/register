from django.db import migrations


IMUTAVEIS = ["core_evento", "vendas_itemvenda", "vendas_pagamento", "vendas_devolucao", "caixa_movimentocaixa"]
FINANCEIROS = ["vendas_venda", "caixa_sessaocaixa"]


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial"), ("vendas", "0002_formas_iniciais"), ("caixa", "0002_initial")]
    operations = [migrations.RunSQL(
        "CREATE FUNCTION pontocar_historico_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Registro historico protegido: use uma operacao de compensacao.'; END; $$",
        "DROP FUNCTION pontocar_historico_imutavel()",
    )] + [migrations.RunSQL(
        f"CREATE TRIGGER proteger_historico BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION pontocar_historico_imutavel()",
        f"DROP TRIGGER proteger_historico ON {table}",
    ) for table in IMUTAVEIS] + [migrations.RunSQL(
        f"CREATE TRIGGER proteger_exclusao BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION pontocar_historico_imutavel()",
        f"DROP TRIGGER proteger_exclusao ON {table}",
    ) for table in FINANCEIROS]
