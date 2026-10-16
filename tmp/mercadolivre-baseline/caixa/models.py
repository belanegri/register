from decimal import Decimal
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q, Sum
from core.models import TimestampedModel


class SessaoCaixa(TimestampedModel):
    operador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2)
    fechado_em = models.DateTimeField(null=True, blank=True)
    saldo_informado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    saldo_esperado_fechamento = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["-pk"]
        verbose_name = "sessão de caixa"
        verbose_name_plural = "sessões de caixa"
        permissions = [("operar_caixa", "Pode abrir e operar o próprio caixa"), ("ver_todos_caixas", "Pode consultar todos os caixas")]
        constraints = [models.UniqueConstraint(fields=["operador"], condition=Q(fechado_em__isnull=True), name="um_caixa_aberto_por_operador"),
            models.CheckConstraint(condition=Q(saldo_inicial__gte=0), name="caixa_abertura_positiva"),
            models.CheckConstraint(condition=Q(saldo_informado__isnull=True) | Q(saldo_informado__gte=0), name="caixa_informado_positivo")]

    @property
    def codigo(self):
        return f"CX-{self.pk:06d}"

    @property
    def saldo_esperado(self):
        return self.saldo_inicial + (self.movimentos.filter(afeta_saldo=True).aggregate(total=Sum("valor"))["total"] or Decimal("0.00"))

    @property
    def diferenca(self):
        if self.fechado_em:
            return self.saldo_informado - self.saldo_esperado_fechamento
        return None

    def __str__(self):
        return self.codigo


class MovimentoCaixa(models.Model):
    chave = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, null=True)
    sessao = models.ForeignKey(SessaoCaixa, on_delete=models.PROTECT, related_name="movimentos")
    criado_em = models.DateTimeField(auto_now_add=True)
    operador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=20, choices=[("venda", "Venda"), ("sangria", "Sangria"), ("suprimento", "Suprimento"), ("estorno", "Estorno")])
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    afeta_saldo = models.BooleanField(default=True)
    descricao = models.CharField(max_length=240)
    venda = models.ForeignKey("vendas.Venda", null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-pk"]
        verbose_name = "movimentação de caixa"
        verbose_name_plural = "movimentações de caixa"
