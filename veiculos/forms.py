import json

from django import forms
from .models import ModeloVeiculo, Veiculo
from .marcas import MARCAS, ALIASES, opcoes_marca


class VeiculoAdminForm(forms.ModelForm):
    marca = forms.ChoiceField(label="Marca")
    modelo = forms.CharField(label="Modelo", max_length=120, widget=forms.Select)

    class Meta:
        model = Veiculo
        fields = "__all__"

    class Media:
        js = ["js/veiculo-form.js"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        catalogo = {marca: [] for marca in MARCAS}
        for marca, modelo in ModeloVeiculo.objects.values_list("marca", "nome"):
            marca = ALIASES.get(marca, marca)
            catalogo.setdefault(marca, []).append(modelo)
        # Mantém editáveis veículos antigos, mesmo após mudanças no catálogo.
        if self.instance.pk:
            modelos = catalogo.setdefault(self.instance.marca, [])
            if self.instance.modelo not in modelos:
                modelos.append(self.instance.modelo)
        self.catalogo = catalogo
        self.fields["marca"].choices = opcoes_marca(self.instance.marca, catalogo)
        self.fields["marca"].widget.attrs["data-modelos"] = json.dumps(catalogo, ensure_ascii=False)
        # Todas as opções agrupadas permitem preenchimento também sem JavaScript.
        self.fields["modelo"].widget.choices = [("", "Selecione o modelo")] + [
            (marca, [(modelo, modelo) for modelo in modelos]) for marca, modelos in catalogo.items()
        ]
        self.fields["modelo"].help_text = "Escolha o modelo. Para marcas sem catálogo, informe o nome do modelo."
        selecionada = self.data.get(self.add_prefix("marca")) if self.is_bound else self.initial.get("marca")
        if selecionada and not catalogo.get(selecionada):
            self.fields["modelo"].widget = forms.TextInput()

    def clean(self):
        data = super().clean()
        marca, modelo = data.get("marca"), data.get("modelo")
        if marca and modelo and self.catalogo.get(marca) and modelo not in self.catalogo[marca]:
            self.add_error("modelo", "Este modelo não pertence à marca selecionada.")
        return data
