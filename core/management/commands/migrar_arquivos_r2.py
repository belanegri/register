"""Copia arquivos referenciados pelo banco, sem apagar as origens."""
import hashlib
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.management.base import BaseCommand, CommandError
from estoque.models import FotoPeca
from contas.models import AnexoConta


def digest(storage, name):
    sha = hashlib.sha256()
    with storage.open(name, "rb") as arquivo:
        for bloco in arquivo.chunks():
            sha.update(bloco)
    return sha.hexdigest()


def copiar(origem, destino, nome):
    esperado = digest(origem, nome)
    if destino.exists(nome):
        if digest(destino, nome) != esperado:
            raise CommandError(f"Conteúdo diferente no destino: {nome}. Nada foi sobrescrito.")
        return False
    with origem.open(nome, "rb") as arquivo:
        salvo = destino.save(nome, arquivo)
    if salvo != nome or digest(destino, salvo) != esperado:
        raise CommandError(f"Falha de verificação: {nome}. Confira o destino antes de continuar.")
    return True


class Command(BaseCommand):
    help = "Simula a transferência local para R2; --executar copia e verifica SHA-256."

    def add_arguments(self, parser):
        parser.add_argument("--executar", action="store_true")

    def handle(self, *args, **options):
        if settings.STORAGE_MODE != "local":
            raise CommandError("Execute na instalação local com STORAGE_MODE=local.")
        grupos = [
            ("fotos", FileSystemStorage(location=settings.MEDIA_ROOT), list(FotoPeca.objects.exclude(imagem="").values_list("imagem", flat=True))),
            ("comprovantes", FileSystemStorage(location=settings.BASE_DIR / ".local" / "comprovantes"), list(AnexoConta.objects.exclude(arquivo="").values_list("arquivo", flat=True))),
        ]
        for prefixo, origem, nomes in grupos:
            for nome in nomes:
                if not origem.exists(nome):
                    raise CommandError(f"Arquivo ausente: {prefixo}/{nome}. Corrija antes da transferência.")
            self.stdout.write(f"{prefixo}: {len(nomes)} arquivos referenciados pelo banco.")
        if not options["executar"]:
            self.stdout.write("Simulação: nenhum arquivo enviado. Use --executar após configurar R2 e fazer backup.")
            return
        from storages.backends.s3 import S3Storage
        env = settings.env
        for prefixo, origem, nomes in grupos:
            destino = S3Storage(access_key=env("R2_ACCESS_KEY_ID"), secret_key=env("R2_SECRET_ACCESS_KEY"),
                bucket_name=env("R2_BUCKET_NAME"), endpoint_url=env("R2_ENDPOINT_URL"), region_name="auto",
                signature_version="s3v4", default_acl=None, file_overwrite=False, location=prefixo)
            for nome in dict.fromkeys(nomes):
                novo = copiar(origem, destino, nome)
                self.stdout.write(f"{'Copiado' if novo else 'Já verificado'}: {prefixo}/{nome}")
        self.stdout.write(self.style.SUCCESS("Transferência verificada. Origens e registros preservados."))
