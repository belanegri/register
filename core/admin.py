from django.contrib import admin
from .models import Evento


class HistoricoAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Evento)
class EventoAdmin(HistoricoAdmin):
    list_display = ["criado_em", "usuario", "acao", "objeto"]
    list_filter = ["acao"]
    search_fields = ["objeto", "usuario__username"]
