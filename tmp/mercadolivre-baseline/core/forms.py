from django import forms
from .models import ConfiguracaoEmpresa


class EstiloForm:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            elif not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = 3


class ConfiguracaoEmpresaForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = ConfiguracaoEmpresa
        fields = ["razao_social", "nome_fantasia", "documento", "inscricao_estadual",
                  "telefone", "whatsapp", "email", "cep", "endereco", "numero",
                  "complemento", "bairro", "cidade", "estado", "logo"]

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and hasattr(logo, "image"):
            if logo.size > 5 * 1024 * 1024:
                raise forms.ValidationError("O logo deve ter até 5 MB.")
            if logo.image.format not in {"PNG", "JPEG", "WEBP"}:
                raise forms.ValidationError("Envie uma imagem PNG, JPEG ou WebP.")
            if logo.image.width * logo.image.height > 16000000 or getattr(logo.image, "is_animated", False):
                raise forms.ValidationError("Envie uma imagem estática de até 16 milhões de pixels.")
        return logo
