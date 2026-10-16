from django.conf import settings
from django.db import models


class Conexao(models.Model):
    # Uma conta por banco/instalação; nunca uma configuração global entre lojas.
    unica = models.BooleanField(default=True, unique=True, editable=False)
    instalacao = models.CharField(max_length=100)
    cliente_id = models.CharField(max_length=80)
    vendedor_id = models.CharField(max_length=30)
    apelido = models.CharField(max_length=200, blank=True)
    escopos = models.TextField(blank=True, editable=False)
    access_token_cifrado = models.TextField(blank=True, editable=False)
    refresh_token_cifrado = models.TextField(blank=True, editable=False)
    expira_em = models.DateTimeField(null=True)
    conectada = models.BooleanField(default=False)
    cursor = models.TextField(blank=True, editable=False)
    cursor_expira_em = models.DateTimeField(null=True, editable=False)
    importacao_concluida = models.BooleanField(default=False)
    ultima_importacao = models.DateTimeField(null=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        permissions = [("gerenciar_integracao", "Gerenciar integração Mercado Livre (somente leitura)")]
        constraints = [models.CheckConstraint(condition=models.Q(unica=True), name="ml_conexao_unica")]


class Anuncio(models.Model):
    conexao = models.ForeignKey(Conexao, on_delete=models.PROTECT, related_name="anuncios")
    item_id = models.CharField(max_length=30)
    titulo = models.CharField(max_length=300)
    status = models.CharField(max_length=40)
    preco = models.DecimalField(max_digits=16, decimal_places=2)
    moeda = models.CharField(max_length=10)
    quantidade = models.PositiveIntegerField()
    vendidos = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=200, blank=True)
    variacoes = models.JSONField(default=list)
    peca = models.ForeignKey("estoque.Peca", on_delete=models.PROTECT, null=True, blank=True,
                             related_name="anuncios_mercadolivre")
    importado_em = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        ordering = ["-importado_em", "item_id"]
        constraints = [models.UniqueConstraint(fields=["conexao", "item_id"], name="ml_anuncio_unico")]


class Selecao(models.Model):
    """Intenção local; não concede autorização para escrita/sincronização na API."""
    peca = models.OneToOneField("estoque.Peca", on_delete=models.CASCADE, related_name="selecao_mercadolivre")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()


class TentativaOAuth(models.Model):
    estado_hash = models.CharField(max_length=64, unique=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expira_em = models.DateTimeField()

    class Meta:
        default_permissions = ()
