from django.contrib import admin
from core.admin import HistoricoAdmin
from .models import SessaoCaixa, MovimentoCaixa


@admin.register(SessaoCaixa)
class SessaoAdmin(HistoricoAdmin):
    list_display = ["codigo", "operador", "criado_em", "fechado_em", "saldo_inicial", "saldo_informado"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.has_perm("caixa.ver_todos_caixas") else qs.filter(operador=request.user)


@admin.register(MovimentoCaixa)
class MovimentoAdmin(HistoricoAdmin):
    list_display = ["criado_em", "sessao", "tipo", "valor", "afeta_saldo", "descricao"]
