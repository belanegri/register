from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Cria os quatro grupos com permissões iniciais (não altera grupos existentes)."

    @transaction.atomic
    def handle(self, *args, **options):
        cadastro = Permission.objects.filter(content_type__app_label__in=["estoque", "veiculos"])
        for nome in ["Administrador", "Gerente", "Caixa", "Vendedor"]:
            group, created = Group.objects.get_or_create(name=nome)
            if created:
                if nome == "Administrador":
                    group.permissions.set(Permission.objects.all())
                elif nome == "Gerente":
                    group.permissions.set(cadastro.exclude(codename__startswith="delete_"))
                else:
                    group.permissions.set(cadastro.filter(codename__startswith="view_"))
            self.stdout.write(f"{nome}: {'criado' if created else 'preservado'}")
