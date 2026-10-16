from django.urls import reverse
from django.utils.html import format_html
from django.contrib import admin
from .models import Categoria, Localizacao, Peca, FotoPeca
from .forms import PecaAdminForm
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

class FotoUploadForm(forms.ModelForm):
    class Meta:
        model = FotoPeca
        fields = "__all__"

    def clean_imagem(self):
        arquivo = self.cleaned_data["imagem"]
        if arquivo and hasattr(arquivo, "content_type"):
            # Valida também a resolução; compressão definitiva acontece no model.
            from PIL import Image
            from django.conf import settings
            try:
                with Image.open(arquivo) as imagem:
                    if imagem.width * imagem.height > settings.PHOTO_MAX_PIXELS or getattr(imagem, "is_animated", False):
                        raise ValidationError("Envie uma foto estática de até 24 megapixels.")
            finally:
                arquivo.seek(0)
        return arquivo

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
        ("Venda online", {"fields": ["postada_online"]}),
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
        campos = ["nome", "preco_venda", "custo", "quantidade", "status", "marca", "aplicacao", "localizacao_id", "postada_online", "compativel"]
        antigo = Peca.objects.get(pk=obj.pk) if change else None
        antes = {c: str(getattr(antigo, c)) for c in campos} if antigo else {}
        super().save_model(request, obj, form, change)
        registrar(request.user, "peca.alterada" if change else "peca.criada", obj.codigo,
            antes=antes, depois={c: str(getattr(obj, c)) for c in campos})

    def has_delete_permission(self, request, obj=None):
        return False
