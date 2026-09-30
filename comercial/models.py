import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import TimestampedModel


class Servico(TimestampedModel):
    nome = models.CharField(max_length=160)
    categoria = models.CharField(
        'categoria/tipo',
        max_length=100,
        blank=True
    )
    descricao = models.TextField(
        'descrição',
        blank=True
    )
    valor_padrao = models.DecimalField(
        'valor padrão',
        max_digits=12,
        decimal_places=2
    )
    ativo = models.BooleanField(default=True)
    observacoes = models.TextField(
        'observações',
        blank=True
    )

    class Meta:
        ordering = ['nome', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_padrao__gte=0),
                name='servico_valor_positivo'
            )
        ]

    @property
    def codigo(self):
        return f'SRV-{self.pk:06d}'

    @property
    def preco_venda(self):
        return self.valor_padrao

    def __str__(self):
        return self.nome


class Documento(TimestampedModel):
    TIPOS = [
        ('orcamento', 'Orçamento'),
        ('os', 'Ordem de serviço'),
    ]

    STATUS = [
        (s, n)
        for s, n in [
            ('rascunho', 'Rascunho'),
            ('enviado', 'Enviado'),
            ('aprovado', 'Aprovado'),
            ('recusado', 'Recusado'),
            ('vencido', 'Vencido'),
            ('convertido', 'Convertido'),
            ('aberta', 'Aberta'),
            ('andamento', 'Em andamento'),
            ('aguardando', 'Aguardando peça'),
            ('finalizada', 'Finalizada'),
            ('entregue', 'Entregue'),
            ('cancelada', 'Cancelada'),
        ]
    ]

    CONDICOES_PAGAMENTO = [
        ('avista', 'À vista'),
        ('parcelado', 'Parcelado'),
    ]

    tipo = models.CharField(
        max_length=12,
        choices=TIPOS
    )

    status = models.CharField(
        max_length=12,
        choices=STATUS
    )

    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.PROTECT,
        related_name='%(class)s_registros'
    )

    veiculo = models.CharField(
        'veículo / marca e modelo',
        max_length=200,
        blank=True
    )

    placa = models.CharField(
        max_length=12,
        blank=True
    )

    ano = models.CharField(
        max_length=20,
        blank=True
    )

    km = models.PositiveIntegerField(
        'KM de entrada',
        null=True,
        blank=True
    )

    combustivel = models.CharField(
        'combustível',
        max_length=60,
        blank=True
    )

    validade = models.DateField(
        null=True,
        blank=True
    )

    previsao = models.DateField(
        'previsão de conclusão',
        null=True,
        blank=True
    )

    conclusao = models.DateField(
        'data de conclusão',
        null=True,
        blank=True
    )

    responsavel = models.CharField(
        'responsável / técnico',
        max_length=160,
        blank=True
    )

    relato = models.TextField(
        'relato do cliente',
        blank=True
    )

    diagnostico = models.TextField(
        'diagnóstico',
        blank=True
    )

    solicitado = models.TextField(
        'serviço solicitado',
        blank=True
    )

    observacoes = models.TextField(
        'observações',
        blank=True
    )

    condicoes = models.TextField(
        'condições',
        blank=True
    )

    desconto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # Condição de pagamento proposta para o documento.
    # No orçamento, estes campos NÃO geram cobrança ou movimento de caixa.
    forma_pagamento = models.ForeignKey(
        'vendas.FormaPagamento',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='documentos_comerciais',
        verbose_name='forma de pagamento',
    )

    condicao_pagamento = models.CharField(
        'condição de pagamento',
        max_length=20,
        choices=CONDICOES_PAGAMENTO,
        default='avista',
    )

    parcelas = models.PositiveSmallIntegerField(
        'parcelas',
        default=1,
    )

    primeiro_vencimento = models.DateField(
        'primeiro vencimento',
        null=True,
        blank=True,
    )

    origem = models.OneToOneField(
        'self',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='ordem_gerada'
    )

    venda = models.OneToOneField(
        'vendas.Venda',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='documento_origem'
    )

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )

    class Meta:
        ordering = ['-pk']
        permissions = [
            (
                'converter_documento',
                'Pode converter orçamento e OS'
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(desconto__gte=0),
                name='documento_desconto_positivo'
            )
        ]

    @property
    def codigo(self):
        return (
            f"{'ORC' if self.tipo == 'orcamento' else 'OS'}"
            f"-{self.pk:06d}"
        )

    @property
    def subtotal_pecas(self):
        return sum(
            (
                i.total
                for i in self.itens.all()
                if i.peca_id
            ),
            Decimal('0')
        )

    @property
    def subtotal_servicos(self):
        return sum(
            (
                i.total
                for i in self.itens.all()
                if i.servico_id
            ),
            Decimal('0')
        )

    @property
    def total(self):
        return (
            self.subtotal_pecas
            + self.subtotal_servicos
            - self.desconto
        )

    @property
    def situacao(self):
        if (
            self.tipo == 'orcamento'
            and self.status in [
                'rascunho',
                'enviado',
                'aprovado'
            ]
            and self.validade
            and self.validade < timezone.localdate()
        ):
            return 'Vencido'

        if self.tipo == 'os' and self.venda_id:
            return 'Convertida em venda'

        return self.get_status_display()

    def __str__(self):
        return self.codigo


class ItemDocumento(models.Model):
    documento = models.ForeignKey(
        Documento,
        on_delete=models.CASCADE,
        related_name='itens'
    )

    peca = models.ForeignKey(
        'estoque.Peca',
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    servico = models.ForeignKey(
        Servico,
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    descricao = models.CharField(
        max_length=240
    )

    quantidade = models.PositiveIntegerField(
        default=1
    )

    preco = models.DecimalField(
        'valor unitário',
        max_digits=12,
        decimal_places=2
    )

    class Meta:
        ordering = ['pk']
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        peca__isnull=False,
                        servico__isnull=True
                    )
                    |
                    Q(
                        peca__isnull=True,
                        servico__isnull=False
                    )
                ),
                name='documento_item_tipo'
            ),
            models.CheckConstraint(
                condition=Q(
                    quantidade__gt=0,
                    preco__gte=0
                ),
                name='documento_item_valor'
            )
        ]

    @property
    def total(self):
        return self.quantidade * self.preco


class ContaReceber(TimestampedModel):
    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.PROTECT,
        related_name='%(class)s_registros'
    )

    descricao = models.CharField(
        'descrição',
        max_length=240
    )

    origem = models.CharField(
        max_length=80,
        default='Manual'
    )

    venda = models.OneToOneField(
        'vendas.Venda',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='conta_receber'
    )

    os = models.ForeignKey(
        Documento,
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    valor_original = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    vencimento = models.DateField()

    cancelada = models.BooleanField(
        default=False
    )

    observacoes = models.TextField(
        'observações',
        blank=True
    )

    class Meta:
        ordering = ['vencimento', 'pk']
        permissions = [
            (
                'receber_conta',
                'Pode registrar recebimentos'
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_original__gt=0),
                name='receber_valor_positivo'
            )
        ]

    @property
    def valor_recebido(self):
        return sum(
            (r.valor for r in self.recebimentos.all()),
            Decimal('0')
        )

    @property
    def saldo(self):
        return self.valor_original - self.valor_recebido

    @property
    def status(self):
        if self.cancelada:
            return 'Cancelada'

        if self.saldo == 0:
            return 'Recebida'

        if self.valor_recebido:
            return 'Parcialmente recebida'

        if self.vencimento < timezone.localdate():
            return 'Vencida'

        return 'A receber'


class Recebimento(models.Model):
    conta = models.ForeignKey(
        ContaReceber,
        on_delete=models.PROTECT,
        related_name='recebimentos'
    )

    chave = models.UUIDField(
        default=uuid.uuid4,
        unique=True
    )

    valor = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    criado_em = models.DateTimeField(
        auto_now_add=True
    )

    forma = models.ForeignKey(
        'vendas.FormaPagamento',
        on_delete=models.PROTECT
    )

    forma_nome = models.CharField(
        max_length=80
    )

    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )

    movimento = models.OneToOneField(
        'caixa.MovimentoCaixa',
        on_delete=models.PROTECT
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(valor__gt=0),
                name='recebimento_positivo'
            )
        ]