from io import BytesIO
from pathlib import Path
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile


def otimizar_foto(arquivo):
    try:
        arquivo.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(arquivo) as origem:
                if origem.width * origem.height > settings.PHOTO_MAX_PIXELS:
                    raise ValidationError("Foto com resolução muito alta. Reduza antes de enviar.")
                if getattr(origem, "is_animated", False):
                    raise ValidationError("Envie uma foto estática.")
                origem.draft("RGB", (settings.PHOTO_MAX_DIMENSION, settings.PHOTO_MAX_DIMENSION))
                imagem = ImageOps.exif_transpose(origem)
                imagem.thumbnail((settings.PHOTO_MAX_DIMENSION, settings.PHOTO_MAX_DIMENSION), Image.Resampling.LANCZOS)
                imagem = imagem.convert("RGBA" if "A" in imagem.getbands() or "transparency" in imagem.info else "RGB")
                saida = BytesIO()
                imagem.save(saida, format="WEBP", quality=settings.PHOTO_WEBP_QUALITY, method=4)
        return ContentFile(saida.getvalue(), name=Path(arquivo.name).stem + ".webp")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError("Imagem inválida ou grande demais para processamento.")
    finally:
        arquivo.seek(0)
