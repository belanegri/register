from django.db import connections, router


def atribuir_codigo(instance, sequencia, prefixo, kwargs, separador="-"):
    """Sequência PostgreSQL atômica, compartilhada entre todos os operadores."""
    if instance.codigo:
        return
    banco = kwargs.get("using") or router.db_for_write(type(instance), instance=instance)
    with connections[banco].cursor() as cursor:
        while True:
            cursor.execute("SELECT nextval(%s::regclass)", [sequencia])
            codigo = f"{prefixo}{separador}{cursor.fetchone()[0]:06d}"
            if not type(instance).objects.using(banco).filter(codigo=codigo).exists():
                instance.codigo = codigo
                break
    if kwargs.get("update_fields") is not None:
        kwargs["update_fields"] = set(kwargs["update_fields"]) | {"codigo"}
