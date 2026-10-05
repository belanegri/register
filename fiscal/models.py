import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import TimestampedModel


class Ambiente(models.TextChoices):
    HOMOLOGACAO = "homologacao", "Homologação"
    PRODUCAO = "producao", "Produção"


class Modelo(models.TextChoices):
    NFE = "55", "NF-e"
    NFCE = "65", "NFC-e"
    NFSE = "nfse", "NFS-e"


class Status(models.TextChoices):
    NAO_SOLICITADA = "nao_solicitada", "Não solicitada"
    PENDENTE = "pendente", "Pendente"
    PROCESSANDO = "processando", "Processando"
    AUTORIZADA = "autorizada", "Autorizada"
    REJEITADA = "rejeitada", "Rejeitada"
    CONTINGENCIA = "contingencia", "Contingência"
    CANCELAMENTO_PENDENTE = "cancelamento_pendente", "Cancelamento pendente"
    CANCELADA = "cancelada", "Cancelada"
    ERRO_TECNICO = "erro_tecnico", "Erro técnico"


digitos = lambda n: RegexValidator(r"^\d{%d}$" % n, f"Informe {n} dígitos.")
aliquota = [MinValueValidator(0), MaxValueValidator(100)]


class ConfiguracaoFiscal(TimestampedModel):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    ativa = models.BooleanField("ativar operações fiscais", default=False)
    ambiente = models.CharField(max_length=12, choices=Ambiente, default=Ambiente.HOMOLOGACAO)
    homologacao_validada = models.BooleanField(default=False)
    producao_validada = models.BooleanField(default=False)
    modelo_mercadorias = models.CharField(max_length=4, choices=[("55", "NF-e"), ("65", "NFC-e")], default="55")
    cnpj = models.CharField(max_length=14, validators=[digitos(14)])
    razao_social = models.CharField(max_length=200)
    nome_fantasia = models.CharField(max_length=200, blank=True)
    ie = models.CharField("inscrição estadual", max_length=30, blank=True)
    im = models.CharField("inscrição municipal", max_length=30, blank=True)
    crt = models.CharField("CRT", max_length=1, choices=[("1", "Simples Nacional"), ("2", "Simples: excesso sublimite"), ("3", "Regime normal"), ("4", "MEI")], default="1")
    uf = models.CharField(max_length=2, validators=[RegexValidator(r"^[A-Z]{2}$")])
    municipio_ibge = models.CharField(max_length=7, validators=[digitos(7)])
    municipio = models.CharField(max_length=100)
    logradouro = models.CharField(max_length=200)
    numero = models.CharField(max_length=20)
    bairro = models.CharField(max_length=100)
    cep = models.CharField(max_length=8, validators=[digitos(8)])
    telefone = models.CharField(max_length=14, blank=True)
    email = models.EmailField(blank=True)
    natureza_operacao = models.CharField(max_length=60, default="Venda de mercadorias")
    csc_id = models.CharField(max_length=6, blank=True, validators=[RegexValidator(r"^\d{1,6}$")])
    qr_code_versao = models.CharField(max_length=1, choices=[('2','2.00 (CSC)'),('3','3.00')], default='3')
    csc_ambiente = models.CharField(max_length=12, choices=Ambiente, default=Ambiente.HOMOLOGACAO, editable=False)
    csc_criptografado = models.BinaryField(blank=True, editable=False)
    certificado_criptografado = models.BinaryField(blank=True, editable=False)
    senha_a1_criptografada = models.BinaryField(blank=True, editable=False)
    certificado_valido_desde = models.DateTimeField(null=True, blank=True, editable=False)
    certificado_valido_ate = models.DateTimeField(null=True, blank=True, editable=False)
    certificado_fingerprint = models.CharField(max_length=64, blank=True, editable=False)
    # Por ambiente/modelo/operação; nunca credenciais ou senhas.
    endpoints = models.JSONField(default=dict, blank=True)
    parametros_nfse = models.JSONField(default=dict, blank=True)

    class Meta:
        permissions = [("configurar_fiscal", "Pode configurar o módulo fiscal")]
        constraints = [models.CheckConstraint(condition=Q(id=1), name="fiscal_config_unica")]

    def __str__(self):
        return "Configuração fiscal desta instalação"

    @property
    def certificado_vencido(self):
        return not self.certificado_valido_ate or self.certificado_valido_ate <= timezone.now()

    def clean(self):
        from .seguranca import validar_endpoints
        validar_endpoints(self.endpoints)
        if self.ambiente == Ambiente.PRODUCAO and not self.producao_validada:
            raise ValidationError({"ambiente": "Valide a homologação e a produção antes de selecionar produção."})
        if self.producao_validada and not self.homologacao_validada:
            raise ValidationError({"producao_validada": "A homologação precisa ser validada primeiro."})


class SequenciaFiscal(models.Model):
    configuracao = models.ForeignKey(ConfiguracaoFiscal, on_delete=models.PROTECT)
    modelo = models.CharField(max_length=4, choices=Modelo)
    ambiente = models.CharField(max_length=12, choices=Ambiente)
    serie = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(999)])
    proximo_numero = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(999999999)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["configuracao", "modelo", "ambiente", "serie"], name="fiscal_sequencia_unica"),
                       models.CheckConstraint(condition=Q(proximo_numero__gte=1, serie__gte=1, serie__lte=999), name="fiscal_sequencia_valida")]

    def __str__(self):
        return f"{self.get_modelo_display()} · {self.get_ambiente_display()} · série {self.serie}"


class ParametroProduto(TimestampedModel):
    peca = models.OneToOneField("estoque.Peca", on_delete=models.PROTECT, related_name="parametro_fiscal")
    ncm = models.CharField(max_length=8, validators=[digitos(8)])
    cfop = models.CharField(max_length=4, validators=[digitos(4)])
    origem = models.CharField(max_length=1, default="0", choices=[(str(n), str(n)) for n in range(9)])
    unidade = models.CharField(max_length=6, default="UN")
    cest = models.CharField(max_length=7, blank=True, validators=[digitos(7)])
    csosn = models.CharField(max_length=3, default="102", validators=[digitos(3)])
    cst_icms = models.CharField(max_length=2, default="00", validators=[digitos(2)])
    aliquota_icms = models.DecimalField(max_digits=7, decimal_places=4, default=0, validators=aliquota)
    cst_pis = models.CharField(max_length=2, default="07", validators=[digitos(2)])
    aliquota_pis = models.DecimalField(max_digits=7, decimal_places=4, default=0, validators=aliquota)
    cst_cofins = models.CharField(max_length=2, default="07", validators=[digitos(2)])
    aliquota_cofins = models.DecimalField(max_digits=7, decimal_places=4, default=0, validators=aliquota)
    tributos_adicionais = models.JSONField(default=dict, blank=True, help_text="Grupos tributários do leiaute oficial, inclusive IBS/CBS quando aplicáveis.")

    def __str__(self):
        return str(self.peca)


class ParametroServico(TimestampedModel):
    servico = models.OneToOneField("comercial.Servico", on_delete=models.PROTECT, related_name="parametro_fiscal")
    item_lista_lc116 = models.CharField(max_length=10)
    codigo_tributacao_nacional = models.CharField(max_length=6, validators=[digitos(6)])
    codigo_tributacao_municipal = models.CharField(max_length=20, blank=True)
    nbs = models.CharField(max_length=9, blank=True, validators=[digitos(9)])
    aliquota_iss = models.DecimalField(max_digits=7, decimal_places=4, default=0, validators=aliquota)
    iss_retido = models.BooleanField(default=False)
    municipio_incidencia = models.CharField(max_length=7, validators=[digitos(7)])
    parametros = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return str(self.servico)


class DocumentoFiscal(TimestampedModel):
    configuracao = models.ForeignKey(ConfiguracaoFiscal, on_delete=models.PROTECT)
    venda = models.ForeignKey("vendas.Venda", null=True, blank=True, on_delete=models.PROTECT, related_name="documentos_fiscais")
    ordem_servico = models.ForeignKey("comercial.Documento", null=True, blank=True, on_delete=models.PROTECT, related_name="documentos_fiscais")
    solicitado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    idempotencia = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    modelo = models.CharField(max_length=4, choices=Modelo)
    ambiente = models.CharField(max_length=12, choices=Ambiente)
    serie = models.PositiveIntegerField()
    tipo_emissao = models.CharField(max_length=1,choices=[('1','Normal'),('9','Contingência offline NFC-e')],default='1',editable=False)
    numero = models.PositiveIntegerField()
    chave_acesso = models.CharField(max_length=50, blank=True, db_index=True)
    identificador_dps = models.CharField(max_length=80, blank=True)
    protocolo = models.CharField(max_length=80, blank=True)
    recibo = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=30, choices=Status, default=Status.NAO_SOLICITADA, db_index=True)
    emitido_em = models.DateTimeField(default=timezone.now)
    autorizado_em = models.DateTimeField(null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    snapshot = models.JSONField(default=dict, editable=False)
    xml_assinado = models.TextField(blank=True, editable=False)
    xml_autorizado = models.TextField(blank=True, editable=False)
    qr_code = models.TextField(blank=True, editable=False)
    codigo_resposta = models.CharField(max_length=20, blank=True)
    mensagem = models.CharField(max_length=500, blank=True)
    transmissao_incerta = models.BooleanField(default=False, editable=False)
    processamento_iniciado_em = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-pk"]
        permissions = [("emitir_fiscal", "Pode solicitar e transmitir documentos fiscais"),
                       ("cancelar_fiscal", "Pode solicitar cancelamentos fiscais"),
                       ("consultar_fiscal", "Pode consultar documentos fiscais e XML"),
                       ("inutilizar_fiscal", "Pode inutilizar numeração fiscal")]
        constraints = [models.UniqueConstraint(fields=["configuracao", "modelo", "ambiente", "serie", "numero"], name="fiscal_numero_unico"),
            models.UniqueConstraint(fields=["venda", "modelo", "ambiente"], condition=Q(venda__isnull=False), name="fiscal_venda_modelo_unico"),
            models.UniqueConstraint(fields=["ordem_servico", "modelo", "ambiente"], condition=Q(ordem_servico__isnull=False), name="fiscal_os_modelo_unico"),
            models.CheckConstraint(condition=Q(venda__isnull=False) | Q(ordem_servico__isnull=False), name="fiscal_documento_origem"),
            models.CheckConstraint(condition=Q(numero__gte=1, serie__gte=1, total__gt=0), name="fiscal_documento_valores")]

    def __str__(self):
        return f"{self.get_modelo_display()} {self.serie}/{self.numero}"

    @property
    def numero_nfse(self):
        if self.modelo!='nfse' or not self.xml_autorizado:return ''
        from .seguranca import xml_seguro, ErroFiscal
        try:
            raiz=xml_seguro(self.xml_autorizado)
            valores=raiz.xpath('.//*[local-name()="nNFSe"]/text()')
            return valores[0] if valores else ''
        except ErroFiscal:return ''


class EventoFiscal(TimestampedModel):
    documento = models.ForeignKey(DocumentoFiscal, null=True, blank=True, on_delete=models.PROTECT, related_name="eventos")
    configuracao = models.ForeignKey(ConfiguracaoFiscal, on_delete=models.PROTECT)
    operador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=20, choices=[("cancelamento", "Cancelamento"), ("inutilizacao", "Inutilização"), ("consulta", "Consulta"), ("contingencia", "Contingência")])
    idempotencia = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=30, choices=Status, default=Status.PENDENTE)
    ambiente = models.CharField(max_length=12, choices=Ambiente)
    modelo = models.CharField(max_length=4, choices=Modelo)
    serie = models.PositiveIntegerField(default=1)
    numero_inicial = models.PositiveIntegerField(null=True, blank=True)
    numero_final = models.PositiveIntegerField(null=True, blank=True)
    ano = models.PositiveSmallIntegerField(null=True, blank=True)
    justificativa = models.CharField(max_length=255, blank=True)
    protocolo = models.CharField(max_length=80, blank=True)
    xml = models.TextField(blank=True, editable=False)
    codigo_resposta = models.CharField(max_length=20, blank=True)
    mensagem = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-pk"]
        constraints = [models.UniqueConstraint(fields=["documento", "tipo"], condition=Q(tipo="cancelamento"), name="fiscal_cancelamento_unico")]


class TentativaTransmissao(models.Model):
    documento = models.ForeignKey(DocumentoFiscal, null=True, blank=True, on_delete=models.PROTECT, related_name="tentativas")
    evento = models.ForeignKey(EventoFiscal, null=True, blank=True, on_delete=models.PROTECT, related_name="tentativas")
    criado_em = models.DateTimeField(auto_now_add=True)
    operacao = models.CharField(max_length=30)
    pedido_sha256 = models.CharField(max_length=64, blank=True)
    resposta = models.TextField(blank=True, editable=False)
    codigo = models.CharField(max_length=20, blank=True)
    mensagem = models.CharField(max_length=500, blank=True)
    erro_tecnico = models.BooleanField(default=False)

    class Meta:
        ordering = ["-pk"]
