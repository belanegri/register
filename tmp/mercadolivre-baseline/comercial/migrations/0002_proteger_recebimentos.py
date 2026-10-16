from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [('comercial', '0001_initial'), ('core', '0002_proteger_historico')]
    operations = [migrations.RunSQL(
        'CREATE TRIGGER proteger_historico BEFORE UPDATE OR DELETE ON comercial_recebimento FOR EACH ROW EXECUTE FUNCTION pontocar_historico_imutavel()',
        'DROP TRIGGER proteger_historico ON comercial_recebimento')]
