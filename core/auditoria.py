from django.conf import settings
from django.db import models


class Evento(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    acao = models.CharField(max_length=80)
    objeto = models.CharField(max_length=120)
    dados = models.JSONField(default=dict)

    class Meta:
        ordering = ["-criado_em", "-pk"]
        verbose_name = "evento de auditoria"
        verbose_name_plural = "auditoria"


def registrar(usuario, acao, objeto, **dados):
    return Evento.objects.create(usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        acao=acao, objeto=str(objeto), dados=dados)
