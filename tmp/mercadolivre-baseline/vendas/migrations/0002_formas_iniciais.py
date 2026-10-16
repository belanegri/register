from django.db import migrations


def cadastrar(apps, schema_editor):
    Forma = apps.get_model("vendas", "FormaPagamento")
    for nome, dinheiro in [("Dinheiro", True), ("PIX", False), ("Cartão de débito", False), ("Cartão de crédito", False)]:
        Forma.objects.using(schema_editor.connection.alias).get_or_create(nome=nome, defaults={"dinheiro": dinheiro})


class Migration(migrations.Migration):
    dependencies = [("vendas", "0001_initial")]
    operations = [migrations.RunPython(cadastrar, migrations.RunPython.noop)]
