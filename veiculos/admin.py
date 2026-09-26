from django.contrib import admin
from .models import Veiculo, ModeloVeiculo
from .forms import VeiculoAdminForm


@admin.register(ModeloVeiculo)
class ModeloVeiculoAdmin(admin.ModelAdmin):
    list_display = ["marca", "nome"]
    list_filter = ["marca"]
    search_fields = ["marca", "nome"]
    readonly_fields = ["criado_em", "atualizado_em"]


@admin.register(Veiculo)
class VeiculoAdmin(admin.ModelAdmin):
    form = VeiculoAdminForm
    list_display = ["codigo", "marca", "modelo", "ano_modelo", "situacao", "data_entrada"]
    list_filter = ["situacao", "marca", "combustivel"]
    search_fields = ["codigo", "marca", "modelo", "versao", "motor"]
    readonly_fields = ["codigo_automatico", "criado_em", "atualizado_em"]
    fields = ["codigo_automatico", "marca", "modelo", "versao", "ano_fabricacao", "ano_modelo",
              "motor", "combustivel", "cambio", "cor", "data_entrada", "observacoes", "situacao",
              "criado_em", "atualizado_em"]
    date_hierarchy = "data_entrada"

    @admin.display(description="Código interno")
    def codigo_automatico(self, obj):
        return obj.codigo if obj and obj.codigo else "Gerado automaticamente ao salvar"
