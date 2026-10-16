from django.db import models
from core.models import TimestampedModel


class Cliente(TimestampedModel):
    nome = models.CharField(max_length=160, db_index=True)
    documento = models.CharField("CPF/CNPJ", max_length=20, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    endereco = models.TextField("endereço", blank=True)
    observacoes = models.TextField("observações", blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome", "pk"]

    def __str__(self):
        return self.nome
