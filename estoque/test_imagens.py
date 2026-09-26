from io import BytesIO
from django.test import SimpleTestCase, override_settings
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from PIL import Image
from .imagens import otimizar_foto
from core.management.commands.migrar_arquivos_r2 import copiar


def foto(tamanho=(2000, 1000), modo="RGB"):
    stream = BytesIO()
    Image.new(modo, tamanho).save(stream, "PNG")
    return ContentFile(stream.getvalue(), name="foto.png")


class ImagemTests(SimpleTestCase):
    def test_redimensiona_converte_sem_metadados(self):
        resultado = otimizar_foto(foto())
        with Image.open(resultado) as imagem:
            self.assertEqual(imagem.format, "WEBP")
            self.assertEqual(imagem.size, (1280, 640))
            self.assertFalse(imagem.getexif())

    def test_preserva_transparencia_e_nao_amplia(self):
        with Image.open(otimizar_foto(foto((50, 40), "RGBA"))) as imagem:
            self.assertEqual(imagem.size, (50, 40))
            self.assertEqual(imagem.getpixel((0, 0))[3], 0)

    @override_settings(PHOTO_MAX_PIXELS=100)
    def test_rejeita_resolucao_excessiva(self):
        with self.assertRaises(ValidationError):
            otimizar_foto(foto((20, 20)))

    def test_rejeita_arquivo_invalido(self):
        with self.assertRaises(ValidationError):
            otimizar_foto(ContentFile(b"invalid", name="foto.jpg"))

    def test_transferencia_idempotente_e_conflito(self):
        origem, destino = InMemoryStorage(), InMemoryStorage()
        origem.save("teste", ContentFile(b"original"))
        self.assertTrue(copiar(origem, destino, "teste"))
        self.assertFalse(copiar(origem, destino, "teste"))
        destino.delete("teste")
        destino.save("teste", ContentFile(b"outro"))
        with self.assertRaises(CommandError):
            copiar(origem, destino, "teste")
        with destino.open("teste") as arquivo:
            self.assertEqual(arquivo.read(), b"outro")
