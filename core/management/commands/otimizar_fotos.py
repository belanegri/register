from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from estoque.models import FotoPeca


class Command(BaseCommand):
    help = "Lista fotos antigas; --executar converte para WebP e preserva os arquivos originais."

    def add_arguments(self, parser):
        parser.add_argument("--executar", action="store_true")

    def handle(self, *args, **options):
        if settings.STORAGE_MODE != "local":
            raise CommandError("Execute localmente antes da transferência para R2.")
        fotos = FotoPeca.objects.exclude(imagem="").exclude(imagem__iendswith=".webp")
        self.stdout.write(f"{fotos.count()} fotos antigas para otimizar.")
        if not options["executar"]:
            self.stdout.write("Simulação: nenhum arquivo ou registro alterado.")
            return
        from django.core.files.base import ContentFile
        for foto in fotos.iterator():
            nome = foto.imagem.name
            with foto.imagem.open("rb") as arquivo:
                foto.imagem = ContentFile(arquivo.read(), name=nome)
            foto.save(update_fields=["imagem"])
            self.stdout.write(f"Foto {foto.pk}: convertida; original preservado.")
