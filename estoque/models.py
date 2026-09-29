import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from core.codigos import atribuir_codigo
from core.models import TimestampedModel


class Categoria(TimestampedModel):
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField("descrição", blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Localizacao(TimestampedModel):
    codigo = models.CharField("código", max_length=40, unique=True, blank=True, editable=False)
    nome = models.CharField(max_length=100)
    pai = models.ForeignKey("self", verbose_name="localização superior", null=True, blank=True,
                            on_delete=models.PROTECT, related_name="sublocalizacoes")
    descricao = models.TextField("descrição", blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "localização"
        verbose_name_plural = "localizações"
        constraints = [models.CheckConstraint(condition=~models.Q(pk=models.F("pai_id")), name="localizacao_nao_e_proprio_pai")]

    def clean(self):
        super().clean()
        visitados = {self.pk} if self.pk else set()
        atual = self.pai
        while atual:
            if atual.pk in visitados:
                raise ValidationError({"pai": "A hierarquia não pode formar um ciclo."})
            visitados.add(atual.pk)
            atual = atual.pai

    def __str__(self):
        return f"{self.codigo} · {self.nome}"


    def save(self, *args, **kwargs):
        atribuir_codigo(self, "estoque_localizacao_codigo_seq", "LOC", kwargs)
        return super().save(*args, **kwargs)


class Peca(TimestampedModel):
    class Status(models.TextChoices):
        DISPONIVEL = "disponivel", "Disponível"
        RESERVADA = "reservada", "Reservada"
        VENDIDA = "vendida", "Vendida"
        BAIXADA = "baixada", "Baixada / indisponível"

    class Condicao(models.TextChoices):
        USADA = "usada", "Usada"
        TESTADA = "testada", "Usada e testada"
        RECONDICIONADA = "recondicionada", "Recondicionada"
        REPARO = "reparo", "Necessita reparo"

    codigo = models.CharField("código interno", max_length=40, unique=True, blank=True, editable=False)
    identificador = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    nome = models.CharField("nome / descrição", max_length=200, db_index=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="pecas")
    veiculo_origem = models.ForeignKey("veiculos.Veiculo", verbose_name="veículo de origem",
        on_delete=models.PROTECT, related_name="pecas", null=True, blank=True)
    marca = models.CharField(max_length=80, blank=True, db_index=True)
    aplicacao = models.CharField("modelo / aplicação", max_length=200, blank=True, db_index=True)
    ano_inicial = models.PositiveSmallIntegerField(null=True, blank=True,
        validators=[MinValueValidator(1900), MaxValueValidator(2100)])
    ano_final = models.PositiveSmallIntegerField(null=True, blank=True,
        validators=[MinValueValidator(1900), MaxValueValidator(2100)])
    motor = models.CharField("motor / aplicação", max_length=80, blank=True)
    posicao = models.CharField("lado / posição", max_length=80, blank=True)
    condicao = models.CharField("condição", max_length=20, choices=Condicao, default=Condicao.USADA)
    localizacao = models.ForeignKey(Localizacao, verbose_name="localização", on_delete=models.PROTECT,
        related_name="pecas", null=True, blank=True)
    custo = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    preco_venda = models.DecimalField("preço de venda", max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    quantidade = models.PositiveIntegerField(default=1)
    observacoes = models.TextField("observações", blank=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.DISPONIVEL, db_index=True)

    class Meta:
        ordering = ["nome", "codigo"]
        verbose_name = "peça"
        verbose_name_plural = "peças"
        indexes = [models.Index(fields=["status", "categoria"], name="peca_status_categoria_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(custo__gte=0), name="peca_custo_nao_negativo"),
            models.CheckConstraint(condition=models.Q(preco_venda__gte=0), name="peca_preco_nao_negativo"),
            models.CheckConstraint(condition=models.Q(ano_inicial__isnull=True) | models.Q(ano_inicial__range=(1900, 2100)), name="peca_ano_inicial_valido"),
            models.CheckConstraint(condition=models.Q(ano_final__isnull=True) | models.Q(ano_final__range=(1900, 2100)), name="peca_ano_final_valido"),
            models.CheckConstraint(condition=models.Q(ano_inicial__isnull=True) | models.Q(ano_final__isnull=True) | models.Q(ano_final__gte=models.F("ano_inicial")), name="peca_intervalo_anos_valido"),
            models.CheckConstraint(condition=~models.Q(status__in=["disponivel", "reservada"]) | models.Q(quantidade__gt=0), name="peca_ativa_tem_quantidade"),
            models.CheckConstraint(condition=~models.Q(status="vendida") | models.Q(quantidade=0), name="peca_vendida_sem_saldo"),
        ]

    def clean(self):
        super().clean()
        if self.ano_inicial and self.ano_final and self.ano_final < self.ano_inicial:
            raise ValidationError({"ano_final": "O ano final deve ser igual ou posterior ao inicial."})
        if self.status in [self.Status.DISPONIVEL, self.Status.RESERVADA] and not self.quantidade:
            raise ValidationError({"quantidade": "Peças disponíveis ou reservadas devem ter saldo."})
        if self.status == self.Status.VENDIDA and self.quantidade != 0:
            raise ValidationError({"quantidade": "Uma peça vendida deve ter saldo zero."})

    def __str__(self):
        return f"{self.codigo} · {self.nome}"

    def save(self, *args, **kwargs):
        atribuir_codigo(self, "estoque_peca_codigo_seq", "REG", kwargs, separador="")
        return super().save(*args, **kwargs)


def caminho_foto(instance, filename):
    return f"pecas/{instance.peca.identificador}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


def validar_tamanho_foto(arquivo):
    if arquivo.size > 5 * 1024 * 1024:
        raise ValidationError("A foto deve ter até 5 MB.")


class FotoPeca(TimestampedModel):
    peca = models.ForeignKey(Peca, on_delete=models.CASCADE, related_name="fotos")
    imagem = models.ImageField(upload_to=caminho_foto, validators=[validar_tamanho_foto])
    legenda = models.CharField(max_length=160, blank=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "pk"]
        verbose_name = "foto da peça"
        verbose_name_plural = "fotos da peça"

    def save(self, *args, **kwargs):
        if self.imagem and not self.imagem._committed:
            from .imagens import otimizar_foto
            validar_tamanho_foto(self.imagem)
            self.imagem = otimizar_foto(self.imagem)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.legenda or f"Foto de {self.peca.codigo}"
