from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from core.models import TimestampedModel
from core.codigos import atribuir_codigo


class ModeloVeiculo(TimestampedModel):
    marca = models.CharField(max_length=80)
    nome = models.CharField("modelo", max_length=120)

    class Meta:
        ordering = ["marca", "nome"]
        verbose_name = "modelo de veículo"
        verbose_name_plural = "marcas e modelos de veículos"
        constraints = [models.UniqueConstraint(fields=["marca", "nome"], name="modelo_unico_por_marca")]

    def __str__(self):
        return f"{self.marca} · {self.nome}"


class Veiculo(TimestampedModel):
    class Situacao(models.TextChoices):
        RECEBIDO = "recebido", "Recebido"
        DESMONTAGEM = "desmontagem", "Em desmontagem"
        DESMONTADO = "desmontado", "Desmontado"
        INATIVO = "inativo", "Inativo"

    codigo = models.CharField("código interno", max_length=40, unique=True, blank=True, editable=False)
    marca = models.CharField(max_length=80, db_index=True)
    modelo = models.CharField(max_length=120, db_index=True)
    versao = models.CharField("versão", max_length=120, blank=True)
    ano_fabricacao = models.PositiveSmallIntegerField("ano de fabricação", null=True, blank=True,
        validators=[MinValueValidator(1900), MaxValueValidator(2100)])
    ano_modelo = models.PositiveSmallIntegerField("ano modelo", null=True, blank=True,
        validators=[MinValueValidator(1900), MaxValueValidator(2100)])
    motor = models.CharField(max_length=80, blank=True)
    combustivel = models.CharField("combustível", max_length=40, blank=True)
    cambio = models.CharField("câmbio", max_length=60, blank=True)
    cor = models.CharField(max_length=50, blank=True)
    data_entrada = models.DateField("data de entrada")
    observacoes = models.TextField("observações", blank=True)
    situacao = models.CharField("situação", max_length=20, choices=Situacao, default=Situacao.RECEBIDO)

    class Meta:
        ordering = ["-data_entrada", "codigo"]
        verbose_name = "veículo de origem"
        verbose_name_plural = "veículos de origem"
        constraints = [
            models.CheckConstraint(condition=models.Q(ano_fabricacao__isnull=True) | models.Q(ano_fabricacao__range=(1900, 2100)), name="veiculo_ano_fabricacao_valido"),
            models.CheckConstraint(condition=models.Q(ano_modelo__isnull=True) | models.Q(ano_modelo__range=(1900, 2100)), name="veiculo_ano_modelo_valido"),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.marca} {self.modelo}"

    def save(self, *args, **kwargs):
        atribuir_codigo(self, "veiculos_veiculo_codigo_seq", "VEI", kwargs)
        return super().save(*args, **kwargs)
