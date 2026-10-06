from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models import TimestampedModel
from .categorias import CATEGORIAS
from decimal import Decimal
import uuid

class ContaPagar(TimestampedModel):
    MODOS = [('unica', 'Conta única'), ('recorrente', 'Recorrente'), ('parcelada', 'Parcelada')]
    from core.parcelamento import FREQUENCIAS
    descricao = models.CharField("descrição", max_length=200, blank=True)
    categoria = models.CharField("categoria", max_length=80, choices=CATEGORIAS, blank=True)
    tipo_conta = models.CharField("tipo de conta", max_length=12, choices=[("residencial", "Residencial"), ("empresa", "Empresa")], blank=True)
    forma_prevista = models.ForeignKey("vendas.FormaPagamento", verbose_name="forma de pagamento", on_delete=models.PROTECT, null=True, blank=True)
    data_programada = models.DateField("data programada de pagamento", null=True, blank=True)
    fornecedor = models.CharField("fornecedor / favorecido", max_length=160)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    valor_original = models.DecimalField('valor original', max_digits=12, decimal_places=2, null=True, blank=True)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    juros = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    multa = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    acrescimos = models.DecimalField('outros acréscimos', max_digits=12, decimal_places=2, default=0)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    subcategoria = models.CharField(max_length=100, blank=True)
    centro_custo = models.CharField('centro de custo', max_length=100, blank=True)
    numero_documento = models.CharField('número do documento', max_length=100, blank=True)
    competencia = models.DateField('competência', null=True, blank=True)
    emissao = models.DateField('data de emissão', null=True, blank=True)
    modo = models.CharField(max_length=12, choices=MODOS, default='unica')
    frequencia = models.CharField(max_length=12, choices=FREQUENCIAS, blank=True)
    lote = models.UUIDField(null=True, blank=True, editable=False)
    parcela = models.PositiveSmallIntegerField(default=1, editable=False)
    total_parcelas = models.PositiveSmallIntegerField(default=1, editable=False)
    vencimento = models.DateField()
    pix_copia_cola = models.TextField("PIX Copia e Cola", blank=True, max_length=4096, help_text="Cole o código de pagamento fornecido pelo recebedor.")
    linha_digitavel = models.CharField(
        "linha digitável",
        max_length=60,
        blank=True,
    )

    codigo_barras = models.CharField(
        "código de barras",
        max_length=60,
        blank=True,
    )
    observacoes = models.TextField("observações", blank=True)
    status = models.CharField(max_length=12, default="pendente", choices=[("pendente","Aguardando"),("parcial","Parcialmente paga"),("paga","Paga"),("cancelada","Cancelada")])
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    pago_em = models.DateField(null=True, blank=True)
    pago_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="contas_pagas")
    forma_nome = models.CharField(max_length=80, blank=True)
    movimento = models.OneToOneField("caixa.MovimentoCaixa", null=True, blank=True, on_delete=models.PROTECT)
    motivo_cancelamento = models.TextField(blank=True)

    class Meta:
        ordering = ["vencimento", "pk"]
        verbose_name = "conta a pagar"
        verbose_name_plural = "contas a pagar"
        constraints = [models.CheckConstraint(condition=models.Q(valor__gt=0), name="conta_valor_positivo"),
            models.UniqueConstraint(fields=['lote', 'parcela'], name='conta_lote_parcela_unica'),
            models.CheckConstraint(condition=models.Q(desconto__gte=0, juros__gte=0, multa__gte=0, acrescimos__gte=0,
                valor_pago__gte=0, valor_pago__lte=models.F('valor')), name='conta_valores_validos'),
            models.CheckConstraint(condition=models.Q(valor_original__isnull=True) | models.Q(
                valor=models.F('valor_original')-models.F('desconto')+models.F('juros')+models.F('multa')+models.F('acrescimos')),
                name='conta_total_consistente')]

    def save(self, *args, **kwargs):
        if self.valor_original is None:
            self.valor_original = self.valor
        self.valor = (Decimal(str(self.valor_original)) - Decimal(str(self.desconto)) + Decimal(str(self.juros))
                      + Decimal(str(self.multa)) + Decimal(str(self.acrescimos)))
        super().save(*args, **kwargs)

    @property
    def saldo(self):
        return self.valor - self.valor_pago

    @property
    def em_aberto(self):
        return self.status in ['pendente', 'parcial']

    @property
    def situacao(self):
        if self.status == 'cancelada':
            return 'Cancelada'
        if self.status == 'paga':
            return 'Paga'
        if self.valor_pago > 0:
            return 'Parcialmente paga'
        if self.atrasada:
            return 'Atrasada'
        return 'Programada' if self.data_programada else 'Aguardando'

    @property
    def codigo(self):
        return f"CP-{self.pk:06d}"

    @property
    def atrasada(self):
        return self.em_aberto and self.vencimento < timezone.localdate()

    @property
    def titulo(self):
        return self.descricao or self.categoria or self.fornecedor

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
    TIPOS = [('cobranca', 'Documento da cobrança'), ('comprovante', 'Comprovante de pagamento'), ('outro', 'Documento anterior / outro')]
    tipo = models.CharField(max_length=12, choices=TIPOS, default='outro')
    pagamento = models.ForeignKey('PagamentoConta', null=True, blank=True, on_delete=models.PROTECT, related_name='anexos')
    conta = models.ForeignKey(ContaPagar, on_delete=models.PROTECT, related_name="anexos")
    arquivo = models.FileField(storage=armazenamento_comprovantes, upload_to=caminho_comprovante, blank=True)
    nome_arquivo = models.CharField(max_length=255, blank=True)
    link = models.URLField(max_length=2000, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-criado_em", "-pk"]


class PagamentoConta(models.Model):
    conta = models.ForeignKey(ContaPagar, on_delete=models.PROTECT, related_name='pagamentos')
    chave = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    data = models.DateField()
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    juros = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    forma = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT)
    forma_nome = models.CharField(max_length=80)
    origem = models.CharField(max_length=10, choices=[('externo', 'Fora do caixa'), ('caixa', 'Caixa')])
    observacao = models.TextField(blank=True)
    operador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    movimento = models.OneToOneField('caixa.MovimentoCaixa', null=True, blank=True, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-data', '-pk']
        constraints = [models.CheckConstraint(condition=models.Q(valor__gt=0, juros__gte=0, desconto__gte=0),
                                             name='pagamento_conta_valores_validos')]
