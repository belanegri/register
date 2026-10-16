from django import forms
from estoque.models import Peca


class VinculoForm(forms.Form):
    codigo = forms.CharField(label="Código exato da peça no REGISTER", max_length=40,
                             widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "REG000001"}))

    def clean_codigo(self):
        try:
            self.peca = Peca.objects.get(codigo__iexact=self.cleaned_data["codigo"].strip())
        except Peca.DoesNotExist:
            raise forms.ValidationError("Nenhuma peça desta loja possui esse código.") from None
        return self.peca.codigo
