import uuid
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
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
    CAMPOS_MERCADO_LIVRE = (
        "ml_titulo", "ml_descricao", "ml_categoria_id", "ml_fabricante", "ml_numero_peca", "ml_oem", "ml_origem",
        "ml_preco", "ml_quantidade", "ml_condicao", "ml_tipo", "ml_envio", "ml_retirada", "ml_frete_gratis", "ml_caracteristicas", "ml_garantia_tipo", "ml_garantia_prazo", "ml_garantia_unidade",
    )
    GARANTIAS_ML = [("2230280", "Garantia do vendedor"), ("2230279", "Garantia de fábrica"), ("6150835", "Sem garantia")]
    UNIDADES_GARANTIA_ML = [("dias", "dias"), ("meses", "meses"), ("anos", "anos")]

    class Status(models.TextChoices):
        DISPONIVEL = "disponivel", "Disponível"
        RESERVADA = "reservada", "Reservada"
        VENDIDA = "vendida", "Vendida"
        BAIXADA = "baixada", "Baixada / indisponível"

    class Condicao(models.TextChoices):
        NOVA = "nova", "Novo"
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
    postada_online = models.BooleanField(
        "Publicada para venda online", default=False,
        help_text="Marque quando a peça estiver anunciada no Mercado Livre, Shopee, OLX ou outros canais.")
    compativel = models.TextField("Compatível", blank=True,
        help_text="Informe veículos, modelos ou outras aplicações compatíveis.")
    observacoes = models.TextField("observações", blank=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.DISPONIVEL, db_index=True)

    classificacao_fiscal_no_estoque = models.BooleanField(default=False, editable=False)
    ncm = models.CharField("NCM", max_length=8, blank=True,
        validators=[RegexValidator(r"\A[0-9]{8}\Z", "Informe os 8 dígitos do NCM.")],
        help_text="Classificação específica desta peça, usada nas notas de entrada e saída.")
    origem_fiscal = models.CharField("Origem fiscal da mercadoria", max_length=1, blank=True,
        choices=[("0", "0 — Nacional"), ("1", "1 — Estrangeira: importação direta"),
                 ("2", "2 — Estrangeira: adquirida no mercado interno"),
                 ("3", "3 — Nacional: conteúdo de importação superior a 40% e até 70%"),
                 ("4", "4 — Nacional: processos produtivos básicos"),
                 ("5", "5 — Nacional: conteúdo de importação até 40%"),
                 ("6", "6 — Estrangeira: importação direta, sem similar nacional"),
                 ("7", "7 — Estrangeira: mercado interno, sem similar nacional"),
                 ("8", "8 — Nacional: conteúdo de importação superior a 70%")],
        help_text="Selecione conforme a procedência comprovada da peça.")
    cest = models.CharField("CEST", max_length=7, blank=True,
        validators=[RegexValidator(r"\A[0-9]{7}\Z", "Informe os 7 dígitos do CEST.")],
        help_text="Preencha quando houver enquadramento. Deixe vazio se não se aplica.")
    classificacao_fiscal_conferida = models.BooleanField("NCM, origem e enquadramento do CEST conferidos", default=False,
        help_text="Confirme após revisar os dados desta peça. Necessário para preparar a nota fiscal.")

    # Preparação local e opcional. Estes campos não selecionam nem publicam a peça.
    ml_titulo = models.CharField("Título do anúncio", max_length=200, blank=True,
        help_text="Se não preencher, será usado o nome da peça. O limite final depende da categoria.")
    ml_descricao = models.TextField("Descrição pública do anúncio", max_length=50000, blank=True,
        help_text="Informe estado, aplicação e itens incluídos. As observações internas não serão copiadas.")
    ml_categoria_id = models.CharField("Categoria no Mercado Livre (código opcional)", max_length=23, blank=True,
        validators=[RegexValidator(r"\AMLB[0-9]{1,20}\Z", "Informe um código de categoria como MLB192572, ou deixe vazio.")],
        help_text="Preencha somente se já souber o código. Você também pode escolher a categoria ao publicar.")
    ml_fabricante = models.CharField("Marca / fabricante da peça", max_length=200, blank=True,
        help_text="Ex.: Bosch, Magneti Marelli ou Cibié. É diferente da marca do veículo.")
    ml_numero_peca = models.CharField("Número / referência da peça", max_length=200, blank=True)
    ml_oem = models.CharField("Código OEM", max_length=200, blank=True)
    ml_origem = models.CharField("Origem da peça", max_length=200, blank=True)
    ml_garantia_tipo = models.CharField("Garantia", max_length=20, blank=True, choices=GARANTIAS_ML)
    ml_garantia_prazo = models.PositiveSmallIntegerField("Prazo de garantia", null=True, blank=True, validators=[MinValueValidator(1)])
    ml_garantia_unidade = models.CharField("Unidade do prazo de garantia", max_length=10, blank=True,
        choices=UNIDADES_GARANTIA_ML, default="dias")
    ml_caracteristicas = models.JSONField("Características secundárias do anúncio", default=dict, blank=True)
    ml_preco = models.DecimalField("Preço para o Mercado Livre (R$)", max_digits=12, decimal_places=2,
        blank=True, null=True, validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Opcional. Se vazio, será sugerido o preço de venda do estoque. Não altera o preço local.")
    ml_quantidade = models.PositiveIntegerField("Quantidade pretendida no anúncio", blank=True, null=True,
        validators=[MinValueValidator(1)], help_text="Se vazio, a sugestão é uma unidade. Na revisão, será limitada ao estoque disponível.")
    ml_condicao = models.CharField("Condição no anúncio", max_length=20, blank=True,
        choices=[("new", "Nova"), ("used", "Usada"), ("not_specified", "Não especificada")],
        help_text="Se vazio, será sugerida a condição cadastrada na peça.")
    ml_tipo = models.CharField("Tipo de anúncio", max_length=20, blank=True,
        choices=[("gold_special", "Clássico"), ("gold_pro", "Premium"), ("free", "Grátis")],
        help_text="A disponibilidade e os custos serão conferidos com o Mercado Livre na publicação.")
    ml_envio = models.CharField("Modalidade de envio", max_length=20, blank=True,
        choices=[("me2", "Mercado Envios"), ("not_specified", "Combinar com o comprador")])
    ml_retirada = models.BooleanField("Permitir retirada pessoal", null=True, blank=True, default=None)
    ml_frete_gratis = models.BooleanField("Oferecer frete grátis", null=True, blank=True, default=None,
        help_text="Os custos e as regras do frete devem ser conferidos antes de publicar.")

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
        if self.classificacao_fiscal_conferida:
            erros = {}
            if not self.ncm: erros["ncm"] = "Informe o NCM antes de confirmar a classificação."
            if not self.origem_fiscal: erros["origem_fiscal"] = "Selecione a origem antes de confirmar a classificação."
            if erros: raise ValidationError(erros)
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
            from .imagens import otimizar_foto, validar_tamanho_envio
            if not getattr(self.imagem.file, "_pontocar_otimizada", False):
                validar_tamanho_envio(self.imagem)
                self.imagem = otimizar_foto(self.imagem, original_celular=True)
            validar_tamanho_foto(self.imagem)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.legenda or f"Foto de {self.peca.codigo}"

