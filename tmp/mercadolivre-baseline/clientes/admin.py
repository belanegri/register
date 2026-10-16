from django.contrib import admin
from .models import Cliente
from core.auditoria import registrar


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ["nome", "documento", "telefone", "ativo"]
    search_fields = ["nome", "documento", "telefone"]
    list_filter = ["ativo"]
    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        registrar(request.user, "cliente.alterado" if change else "cliente.criado", f"Cliente {obj.pk}", campos=form.changed_data)
