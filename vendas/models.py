import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from decimal import Decimal
from core.models import TimestampedModel


class FormaPagamento(TimestampedModel):
    nome = models.CharField(max_length=80, unique=True)
    dinheiro = models.BooleanField("movimenta dinheiro físico", default=False)
    ativa = models.BooleanField(default=True)
    promissoria = models.BooleanField("gera nota promissória (a receber)", default=False)

    class Meta:
        ordering = ["nome"]
        verbose_name = "forma de pagamento"
        verbose_name_plural = "formas de pagamento"
        constraints = [models.CheckConstraint(condition=~Q(dinheiro=True, promissoria=True), name="forma_promissoria_nao_dinheiro")]

    def __str__(self):
        return self.nome


class Venda(models.Model):
    substitui = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="substituta")
    chave = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    vendedor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    cliente = models.ForeignKey("clientes.Cliente", null=True, blank=True, on_delete=models.PROTECT, related_name="vendas")
    cliente_nome = models.CharField(max_length=160, blank=True)
    caixa = models.ForeignKey("caixa.SessaoCaixa", on_delete=models.PROTECT)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, default="concluida", choices=[("concluida", "Concluída"),
        ("parcial", "Devolução parcial"), ("devolvida", "Devolvida"), ("cancelada", "Cancelada")])
    motivo_cancelamento = models.TextField(blank=True)

    class Meta:
        ordering = ["-pk"]
        permissions = [("editar_venda", "Pode corrigir vendas concluídas"), ("receber_promissoria", "Pode receber notas promissórias"), ("usar_pdv", "Pode finalizar vendas no PDV"), ("cancelar_venda", "Pode cancelar vendas"),
            ("devolver_venda", "Pode registrar devoluções"), ("ver_relatorios", "Pode consultar relatórios"),
            ("ver_todas_vendas", "Pode consultar vendas de todos os operadores"), ("dar_desconto", "Pode conceder desconto")]
        constraints = [models.CheckConstraint(condition=Q(total__gt=0), name="venda_total_positivo"),
            models.CheckConstraint(condition=Q(desconto__gte=0) & Q(desconto__lte=models.F("subtotal")), name="venda_desconto_valido"),
            models.CheckConstraint(condition=Q(total=models.F("subtotal")-models.F("desconto")), name="venda_total_consistente")]

    @property
    def codigo(self):
        return f"VEN-{self.pk:06d}"

    def __str__(self):
        return self.codigo


class ItemVenda(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.PROTECT, related_name="itens")
    peca = models.ForeignKey("estoque.Peca", on_delete=models.PROTECT)
    descricao = models.CharField(max_length=240)
    quantidade = models.PositiveIntegerField()
    preco_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    custo_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantidade__gt=0), name="item_quantidade_positiva"),
            models.UniqueConstraint(fields=["venda", "peca"], name="item_peca_unica_por_venda")]

    @property
    def quantidade_devolvida(self):
        return sum(d.quantidade for d in self.devolucoes.all())

    @property
    def quantidade_restante(self):
        return self.quantidade - self.quantidade_devolvida


class Pagamento(models.Model):
    promissoria = models.BooleanField(default=False)
    venda = models.ForeignKey(Venda, on_delete=models.PROTECT, related_name="pagamentos")
    forma = models.ForeignKey(FormaPagamento, on_delete=models.PROTECT)
    forma_nome = models.CharField(max_length=80)
    dinheiro = models.BooleanField()
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    recebido = models.DecimalField(max_digits=12, decimal_places=2)
    troco = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(valor__gt=0) & Q(troco__gte=0), name="pagamento_valores_validos"),
            models.CheckConstraint(condition=(Q(promissoria=False) & Q(recebido=models.F("valor")+models.F("troco"))) | Q(promissoria=True, recebido=0, troco=0, dinheiro=False), name="pagamento_troco_consistente")]


class Devolucao(models.Model):
    abatimento_promissoria = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    chave = models.UUIDField(unique=True, default=uuid.uuid4)
    item = models.ForeignKey(ItemVenda, on_delete=models.PROTECT, related_name="devolucoes")
    criado_em = models.DateTimeField(auto_now_add=True)
    operador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    quantidade = models.PositiveIntegerField()
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    motivo = models.TextField()
    forma = models.ForeignKey(FormaPagamento, on_delete=models.PROTECT)
    forma_nome = models.CharField(max_length=80)
    dinheiro = models.BooleanField()
    caixa = models.ForeignKey("caixa.SessaoCaixa", on_delete=models.PROTECT)

    class Meta:
        verbose_name = "devolução"
        verbose_name_plural = "devoluções"
        constraints = [models.CheckConstraint(condition=Q(quantidade__gt=0) & Q(valor__gte=0), name="devolucao_valida")]

    @property
    def reembolsado(self):
        return self.valor - self.abatimento_promissoria


class NotaPromissoria(models.Model):
    pagamento = models.OneToOneField(Pagamento, on_delete=models.PROTECT, related_name="nota")
    emitida_em = models.DateField()
    vencimento = models.DateField()
    emitente = models.CharField(max_length=160)
    documento = models.CharField(max_length=20)
    endereco = models.TextField(blank=True)
    beneficiario = models.CharField(max_length=160)
    documento_beneficiario = models.CharField(max_length=20, blank=True)
    local_emissao = models.CharField(max_length=160)
    local_pagamento = models.CharField(max_length=200)

    class Meta:
        ordering = ["vencimento", "pk"]
        verbose_name = "nota promissória"
        verbose_name_plural = "notas promissórias"

    @property
    def codigo(self):
        return f"NP-{self.pk:06d}"

    @property
    def saldo(self):
        return self.pagamento.valor - sum((m.valor for m in self.movimentos.all()), Decimal("0"))

    def __str__(self):
        return self.codigo


class MovimentoPromissoria(models.Model):
    chave = models.UUIDField(default=uuid.uuid4, unique=True)
    nota = models.ForeignKey(NotaPromissoria, on_delete=models.PROTECT, related_name="movimentos")
    criado_em = models.DateTimeField(auto_now_add=True)
    operador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    caixa = models.ForeignKey("caixa.SessaoCaixa", on_delete=models.PROTECT)
    tipo = models.CharField(max_length=12, choices=[("recebido", "Recebimento"), ("abatido", "Abatimento por cancelamento/devolução")])
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    forma = models.ForeignKey(FormaPagamento, null=True, on_delete=models.PROTECT)
    forma_nome = models.CharField(max_length=80, blank=True)
    dinheiro = models.BooleanField(default=False)
    motivo = models.CharField(max_length=240, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(valor__gt=0), name="movimento_promissoria_positivo")]
