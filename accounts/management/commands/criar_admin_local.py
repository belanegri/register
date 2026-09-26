import secrets
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Cria admin de desenvolvimento com senha aleatória em .local/ACESSO_LOCAL.txt."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Comando permitido apenas em desenvolvimento.")
        user_model = get_user_model()
        if user_model.objects.filter(username="admin").exists():
            self.stdout.write("Usuário admin existente preservado; nenhuma senha alterada.")
            return
        password = secrets.token_urlsafe(18)
        user_model.objects.create_superuser(username="admin", password=password)
        path = Path(settings.BASE_DIR) / ".local" / "ACESSO_LOCAL.txt"
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"PontoCar — acesso de desenvolvimento\n\nEndereço: http://127.0.0.1:8000/\n"
            f"Usuário: admin\nSenha: {password}\n\nAltere sua senha em /conta/senha/ após entrar.\n"
            "Cada funcionário deve receber seu próprio usuário. Não compartilhe este arquivo.\n", encoding="utf-8")
        self.stdout.write("Admin criado. Consulte .local/ACESSO_LOCAL.txt para a senha inicial.")
