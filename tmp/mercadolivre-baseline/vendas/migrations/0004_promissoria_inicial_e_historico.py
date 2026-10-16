from django.db import migrations


def criar_forma(apps, schema_editor):
    apps.get_model('vendas', 'FormaPagamento').objects.get_or_create(
        nome='Nota promissória', defaults={'promissoria': True, 'dinheiro': False, 'ativa': True})


class Migration(migrations.Migration):
    dependencies = [('vendas', '0003_movimentopromissoria_notapromissoria_and_more'), ('core', '0002_proteger_historico')]
    operations = [migrations.RunPython(criar_forma, migrations.RunPython.noop)] + [
        migrations.RunSQL(
            f'CREATE TRIGGER proteger_historico BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION pontocar_historico_imutavel()',
            f'DROP TRIGGER proteger_historico ON {table}',
        ) for table in ['vendas_notapromissoria', 'vendas_movimentopromissoria']
    ]
