from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Adiciona permissões dos novos módulos aos grupos existentes, preservando as demais."

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("configurar_grupos")
        basicas = {
            "comercial": ["view_servico", "view_documento", "add_documento", "change_documento", "converter_documento"],
            "clientes": ["view_cliente", "add_cliente", "change_cliente"],
            "vendas": ["usar_pdv", "view_venda", "view_formapagamento", "receber_promissoria"],
            "caixa": ["operar_caixa", "view_sessaocaixa"],
        }
        gestao = {"comercial": ["add_servico", "change_servico", "view_contareceber", "add_contareceber", "change_contareceber", "receber_conta"], "contas": ["view_contapagar", "add_contapagar", "change_contapagar"], "vendas": ["editar_venda", "cancelar_venda", "devolver_venda", "dar_desconto", "ver_relatorios", "ver_todas_vendas", "add_formapagamento", "change_formapagamento"],
                  "caixa": ["ver_todos_caixas", "view_movimentocaixa"], "core": ["view_evento"]}
        for nome in ["Administrador", "Gerente", "Caixa", "Vendedor"]:
            grupo = Group.objects.get(name=nome)
            for app, codigos in basicas.items():
                grupo.permissions.add(*Permission.objects.filter(content_type__app_label=app, codename__in=codigos))
            if nome in ["Administrador", "Gerente"]:
                for app, codigos in gestao.items():
                    grupo.permissions.add(*Permission.objects.filter(content_type__app_label=app, codename__in=codigos))
            if nome == "Administrador":
                grupo.permissions.add(*Permission.objects.filter(content_type__app_label__in=["vendas", "caixa", "clientes", "core"]))
        self.stdout.write("Permissões operacionais adicionadas aos quatro grupos.")
