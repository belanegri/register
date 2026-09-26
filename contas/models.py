from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models import TimestampedModel
from .categorias import CATEGORIAS

class ContaPagar(TimestampedModel):
    descricao = models.CharField("descrição", max_length=200, blank=True)
    categoria = models.CharField("categoria", max_length=80, choices=CATEGORIAS, blank=True)
    tipo_conta = models.CharField("tipo de conta", max_length=12, choices=[("residencial", "Residencial"), ("empresa", "Empresa")], blank=True)
    forma_prevista = models.ForeignKey("vendas.FormaPagamento", verbose_name="forma de pagamento", on_delete=models.PROTECT, null=True, blank=True)
    data_programada = models.DateField("data programada de pagamento", null=True, blank=True)
    fornecedor = models.CharField("fornecedor / favorecido", max_length=160)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    vencimento = models.DateField()
    pix_copia_cola = models.TextField("PIX Copia e Cola", blank=True, max_length=4096, help_text="Cole o código de pagamento fornecido pelo recebedor.")
    observacoes = models.TextField("observações", blank=True)
    status = models.CharField(max_length=12, default="pendente", choices=[("pendente","Pendente"),("paga","Paga"),("cancelada","Cancelada")])
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    pago_em = models.DateField(null=True, blank=True)
    pago_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="contas_pagas")
    forma_nome = models.CharField(max_length=80, blank=True)
    movimento = models.OneToOneField("caixa.MovimentoCaixa", null=True, blank=True, on_delete=models.PROTECT)
    motivo_cancelamento = models.TextField(blank=True)

    class Meta:
        ordering = ["vencimento", "pk"]
        verbose_name = "conta a pagar"
        verbose_name_plural = "contas a pagar"
        constraints = [models.CheckConstraint(condition=models.Q(valor__gt=0), name="conta_valor_positivo")]

    @property
    def codigo(self):
        return f"CP-{self.pk:06d}"

    @property
    def atrasada(self):
        return self.status == "pendente" and self.vencimento < timezone.localdate()

    @property
    def titulo(self):
        return self.categoria or self.descricao or self.fornecedor

    def __str__(self):
        return f"{self.codigo} · {self.titulo}"


# Comprovantes ficam fora da pasta de mídia pública; download exige permissão.
def armazenamento_comprovantes():
    from django.core.files.storage import storages
    return storages["comprovantes"]


def caminho_comprovante(instance, filename):
    import uuid
    from pathlib import Path
    return f"{instance.conta_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class AnexoConta(models.Model):
    conta = models.ForeignKey(ContaPagar, on_delete=models.PROTECT, related_name="anexos")
    arquivo = models.FileField(storage=armazenamento_comprovantes, upload_to=caminho_comprovante, blank=True)
    nome_arquivo = models.CharField(max_length=255, blank=True)
    link = models.URLField(max_length=2000, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-criado_em", "-pk"]
