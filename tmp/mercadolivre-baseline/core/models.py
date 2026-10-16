from django.db import models
from .auditoria import Evento


class TimestampedModel(models.Model):
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


def caminho_logo_empresa(instance, filename):
    from pathlib import Path
    from uuid import uuid4
    return f"empresa/logos/{uuid4().hex}{Path(filename).suffix.lower()}"


class ConfiguracaoEmpresa(TimestampedModel):
    unica = models.BooleanField(default=True, unique=True, editable=False)
    razao_social = models.CharField("razão social", max_length=200, blank=True)
    nome_fantasia = models.CharField("nome fantasia", max_length=200, blank=True)
    documento = models.CharField("CNPJ/CPF", max_length=20, blank=True)
    inscricao_estadual = models.CharField("inscrição estadual", max_length=30, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField("WhatsApp", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    cep = models.CharField("CEP", max_length=9, blank=True)
    endereco = models.CharField("endereço", max_length=200, blank=True)
    numero = models.CharField("número", max_length=20, blank=True)
    complemento = models.CharField(max_length=100, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    estado = models.CharField("estado", max_length=2, blank=True,
        choices=[(uf, uf) for uf in "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()])
    logo = models.ImageField(upload_to=caminho_logo_empresa, blank=True)

    class Meta:
        verbose_name = "configuração da empresa"
        verbose_name_plural = "configurações da empresa"
        default_permissions = ("view", "change")
        constraints = [models.CheckConstraint(condition=models.Q(unica=True), name="configuracao_empresa_unica_true")]

    def __str__(self):
        return self.nome_fantasia or self.razao_social or "Configurações da Empresa"
