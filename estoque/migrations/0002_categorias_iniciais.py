from django.db import migrations


CATEGORIAS = (
    "Motor",
    "Alimentação e Injeção",
    "Admissão de Ar",
    "Turbo e Sobrealimentação",
    "Arrefecimento",
    "Lubrificação",
    "Ignição",
    "Escapamento",
    "Câmbio e Transmissão",
    "Embreagem",
    "Suspensão",
    "Direção",
    "Freios",
    "Rodas e Pneus",
    "Elétrica",
    "Eletrônica e Módulos",
    "Sensores",
    "Iluminação",
    "Lataria e Carroceria",
    "Para-choques e Acabamentos Externos",
    "Retrovisores",
    "Vidros",
    "Máquinas de Vidro",
    "Fechaduras e Travas",
    "Interior e Acabamento",
    "Bancos",
    "Cintos e Segurança",
    "Airbag",
    "Painel e Instrumentos",
    "Comandos e Chaves",
    "Ar-condicionado e Climatização",
    "Áudio e Multimídia",
    "Limpadores e Lavadores",
    "Acessórios",
    "Fixadores e Suportes",
    "Outros / Diversos",
)


def cadastrar_categorias(apps, schema_editor):
    categoria = apps.get_model("estoque", "Categoria")
    for nome in CATEGORIAS:
        categoria.objects.using(schema_editor.connection.alias).get_or_create(
            nome=nome, defaults={"ativa": True}
        )


class Migration(migrations.Migration):
    dependencies = [("estoque", "0001_initial")]
    operations = [
        # Preserva os cadastros e eventuais vínculos com peças ao reverter.
        migrations.RunPython(cadastrar_categorias, migrations.RunPython.noop),
    ]
