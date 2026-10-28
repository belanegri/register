from django.urls import reverse
from django.utils.html import format_html
from django.contrib import admin
from .models import Categoria, Localizacao, Peca, FotoPeca
from .forms import PecaAdminForm
from mercadolivre.atributos import CAMPOS_CARACTERISTICAS
from core.auditoria import registrar


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nome", "ativa"]
    list_filter = ["ativa"]
    search_fields = ["nome"]
    readonly_fields = ["criado_em", "atualizado_em"]


@admin.register(Localizacao)
class LocalizacaoAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nome", "pai", "ativa"]
    list_filter = ["ativa"]
    search_fields = ["codigo", "nome"]
    autocomplete_fields = ["pai"]
    list_select_related = ["pai"]
    readonly_fields = ["codigo_automatico", "criado_em", "atualizado_em"]
    fields = ["codigo_automatico", "nome", "pai", "descricao", "ativa", "criado_em", "atualizado_em"]

    @admin.display(description="Código")
    def codigo_automatico(self, obj):
        return obj.codigo if obj and obj.codigo else "Gerado automaticamente ao salvar"


from django.core.exceptions import ValidationError


from django import forms

class FotoCelularField(forms.FileField):
    def to_python(self, data):
        arquivo = super().to_python(data)
        if not arquivo:
            return arquivo
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .imagens import otimizar_foto, validar_tamanho_envio
        validar_tamanho_envio(arquivo)
        convertido = otimizar_foto(arquivo, original_celular=True)
        resultado = SimpleUploadedFile(convertido.name, convertido.read(), content_type="image/webp")
        resultado._pontocar_otimizada = True
        return resultado


class FotoUploadForm(forms.ModelForm):
    imagem = FotoCelularField(required=False, label="Imagem",
        help_text="Fotos do celular, inclusive HEIC/HEIF, são reduzidas automaticamente. Original: até 25 MB e 50 megapixels.",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*,.heic,.heif"}))

    class Meta:
        model = FotoPeca
        fields = "__all__"

    class Media:
        js = ["js/fotos-celular.js"]


class FotoPecaInline(admin.TabularInline):
    model = FotoPeca
    min_num = 0
    form = FotoUploadForm
    extra = 1


@admin.register(Peca)
class PecaAdmin(admin.ModelAdmin):
    form = PecaAdminForm
    list_display = ["codigo", "nome", "categoria", "aplicacao", "localizacao", "preco_venda", "quantidade", "status"]
    list_filter = ["status", "categoria", "condicao", "marca"]
    search_fields = ["codigo", "nome", "categoria__nome", "marca", "aplicacao", "motor", "posicao",
        "veiculo_origem__codigo", "veiculo_origem__marca", "veiculo_origem__modelo", "localizacao__codigo", "localizacao__nome"]
    autocomplete_fields = ["categoria", "veiculo_origem", "localizacao"]
    list_select_related = ["categoria", "veiculo_origem", "localizacao"]
    readonly_fields = ["codigo_automatico", "codigo_barras", "identificador", "criado_em", "atualizado_em"]
    inlines = [FotoPecaInline]
    fieldsets = [
        ("Identificação", {"fields": ["versao_estoque", "codigo_automatico", "codigo_barras", "nome", "marca", "aplicacao", "categoria", "veiculo_origem"]}),
        ("Aplicação", {"fields": [("ano_inicial", "ano_final"), "motor", "posicao", "compativel"]}),
        ("Estoque e valores", {"fields": ["condicao", "localizacao", "custo", "preco_venda", "quantidade", "status"]}),
        ("Classificação fiscal da peça", {"fields": ["ncm", "origem_fiscal", "cest", "classificacao_fiscal_conferida"]}),
        ("Venda online", {"fields": ["postada_online"]}),
        ("Preparar anúncio no Mercado Livre (opcional)", {
            "classes": ["collapse"],
            "description": "Adiante os dados do anúncio, mesmo sem conta conectada. Salvar não publica nem seleciona a peça. Na publicação manual você poderá revisar e alterar tudo.",
            "fields": ["ml_sku", "ml_titulo", "ml_descricao", ("ml_fabricante", "ml_numero_peca"),
                       ("ml_preco", "ml_quantidade"), ("ml_condicao", "ml_tipo"), "ml_categoria_id", "ml_envio",
                       ("ml_retirada", "ml_frete_gratis"), "ml_garantia_tipo", ("ml_garantia_prazo", "ml_garantia_unidade")],
        }),
        ("Características secundárias do anúncio", {
            "classes": ["collapse"],
            "description": "Preencha as características aplicáveis à peça. Use Não se aplica somente quando correto. Na publicação, serão usadas as características aceitas pela categoria escolhida.",
            "fields": list(CAMPOS_CARACTERISTICAS),
        }),
        ("Informações adicionais", {"fields": ["observacoes", "identificador", "criado_em", "atualizado_em"]}),
    ]

    @admin.display(description="Código interno")
    def codigo_automatico(self, obj):
        return obj.codigo if obj and obj.codigo else "Gerado automaticamente ao salvar"

    @admin.display(description="Código de barras")
    def codigo_barras(self, obj):
        if not obj or not obj.pk:
            return "Disponível após salvar a peça."
        return format_html('<img src="{}" alt="Código de barras {}" style="max-width:100%;width:260px;height:65px;object-fit:contain;background:white"><br><a href="{}" target="_blank" rel="noopener">Imprimir etiqueta</a>',
            reverse("estoque:codigo_barras", args=[obj.pk]), obj.codigo,
            reverse("estoque:etiqueta", args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        campos = ["nome", "preco_venda", "custo", "quantidade", "status", "marca", "aplicacao", "localizacao_id", "postada_online", "compativel", "ncm", "origem_fiscal", "cest", "classificacao_fiscal_conferida"]
        campos += list(Peca.CAMPOS_MERCADO_LIVRE)
        antigo = Peca.objects.get(pk=obj.pk) if change else None
        antes = {c: str(getattr(antigo, c)) for c in campos} if antigo else {}
        super().save_model(request, obj, form, change)
        registrar(request.user, "peca.alterada" if change else "peca.criada", obj.codigo,
            antes=antes, depois={c: str(getattr(obj, c)) for c in campos})

    def has_delete_permission(self, request, obj=None):
        return False
