from django.db import migrations


def adicionar_boleto(apps, schema_editor):
    apps.get_model('vendas', 'FormaPagamento').objects.using(schema_editor.connection.alias).get_or_create(
        nome='Boleto parcelado', defaults={'dinheiro': False, 'promissoria': False, 'ativa': True})


class Migration(migrations.Migration):
    dependencies = [('vendas', '0006_itemvenda_servico_alter_itemvenda_peca_and_more')]
    operations = [migrations.RunPython(adicionar_boleto, migrations.RunPython.noop)]
