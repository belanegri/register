from django.contrib import admin
from core.admin import HistoricoAdmin
from .models import FormaPagamento, Venda, ItemVenda, Pagamento, Devolucao, NotaPromissoria, MovimentoPromissoria
from core.auditoria import registrar


@admin.register(FormaPagamento)
class FormaAdmin(admin.ModelAdmin):
    list_display = ["nome", "dinheiro", "promissoria", "ativa"]
    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        registrar(request.user, "pagamento.configuracao", f"Forma {obj.pk}", nome=obj.nome, dinheiro=obj.dinheiro, ativa=obj.ativa)


@admin.register(Venda)
class VendaAdmin(HistoricoAdmin):
    list_display = ["codigo", "criado_em", "vendedor", "cliente_nome", "total", "status"]
    list_filter = ["status", "vendedor"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.has_perm("vendas.ver_todas_vendas") else qs.filter(vendedor=request.user)


admin.site.register(ItemVenda, HistoricoAdmin)
admin.site.register(Pagamento, HistoricoAdmin)
admin.site.register(Devolucao, HistoricoAdmin)
admin.site.register(NotaPromissoria, HistoricoAdmin)
admin.site.register(MovimentoPromissoria, HistoricoAdmin)
