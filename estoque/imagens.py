from io import BytesIO
from pathlib import Path
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from pillow_heif import register_heif_opener

register_heif_opener(thumbnails=False)


def validar_tamanho_envio(arquivo):
    if arquivo.size > settings.PHOTO_UPLOAD_MAX_BYTES:
        limite = settings.PHOTO_UPLOAD_MAX_BYTES // (1024 * 1024)
        raise ValidationError(f"A foto original deve ter até {limite} MB.")


def otimizar_foto(arquivo, *, original_celular=False):
    try:
        arquivo.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(arquivo) as origem:
                limite_pixels = settings.PHOTO_UPLOAD_MAX_PIXELS if original_celular else settings.PHOTO_MAX_PIXELS
                if origem.width * origem.height > limite_pixels:
                    raise ValidationError("Foto com resolução muito alta. Escolha uma foto em resolução menor.")
                if getattr(origem, "is_animated", False) and origem.format not in ("HEIF", "HEIC"):
                    raise ValidationError("Envie uma foto estática.")
                origem.draft("RGB", (settings.PHOTO_MAX_DIMENSION, settings.PHOTO_MAX_DIMENSION))
                # Reduz antes de copiar/rotacionar: evita duplicar uma foto de 48 MP na memória.
                origem.thumbnail((settings.PHOTO_MAX_DIMENSION, settings.PHOTO_MAX_DIMENSION), Image.Resampling.LANCZOS)
                imagem = ImageOps.exif_transpose(origem)
                imagem = imagem.convert("RGBA" if "A" in imagem.getbands() or "transparency" in imagem.info else "RGB")
                saida = BytesIO()
                imagem.save(saida, format="WEBP", quality=settings.PHOTO_WEBP_QUALITY, method=4)
        return ContentFile(saida.getvalue(), name=Path(arquivo.name).stem + ".webp")
    except (UnidentifiedImageError, OSError, ValueError, RuntimeError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError("Imagem inválida ou grande demais para processamento.")
    finally:
        arquivo.seek(0)
