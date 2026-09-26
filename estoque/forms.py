import json

from django import forms
from veiculos.marcas import MARCAS, ALIASES, opcoes_marca
from veiculos.models import ModeloVeiculo
from .models import Peca
from core.forms import EstiloForm


class PecaAdminForm(forms.ModelForm):
    versao_estoque = forms.CharField(required=False, widget=forms.HiddenInput)
    marca = forms.ChoiceField(label="Marca", required=False)
    aplicacao = forms.CharField(label="Modelo / aplicação", required=False, max_length=200, widget=forms.Select)

    class Meta:
        model = Peca
        fields = "__all__"

    class Media:
        js = ["js/veiculo-form.js"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["versao_estoque"].initial = self.instance.atualizado_em.isoformat()
        catalogo = {marca: [] for marca in MARCAS}
        for marca, modelo in ModeloVeiculo.objects.values_list("marca", "nome"):
            catalogo.setdefault(ALIASES.get(marca, marca), []).append(modelo)
        if self.instance.pk and self.instance.aplicacao:
            modelos = catalogo.setdefault(self.instance.marca, [])
            if self.instance.aplicacao not in modelos:
                modelos.append(self.instance.aplicacao)
        self.catalogo = catalogo
        self.fields["marca"].choices = opcoes_marca(self.instance.marca, catalogo)
        self.fields["marca"].widget.attrs.update({
            "data-modelos": json.dumps(catalogo, ensure_ascii=False),
            "data-modelo-campo": self["aplicacao"].auto_id,
            "data-modelo-maxlength": "200",
        })
        self.fields["aplicacao"].widget.choices = [("", "Selecione o modelo")] + [
            (marca, [(modelo, modelo) for modelo in modelos]) for marca, modelos in catalogo.items()
        ]
        self.fields["aplicacao"].help_text = "Escolha o modelo da marca. Para marcas sem catálogo, informe o modelo."
        selecionada = self.data.get(self.add_prefix("marca")) if self.is_bound else self.initial.get("marca")
        if selecionada and not catalogo.get(selecionada):
            self.fields["aplicacao"].widget = forms.TextInput()

    def clean(self):
        data = super().clean()
        if self.instance.pk:
            atual = Peca.objects.select_for_update().get(pk=self.instance.pk)
            if data.get("versao_estoque") != atual.atualizado_em.isoformat():
                raise forms.ValidationError("Esta peça foi alterada por outra operação. Recarregue a página antes de salvar.")
        marca, modelo = data.get("marca"), data.get("aplicacao")
        if modelo and not marca and not (
            self.instance.pk and not self.instance.marca and modelo == self.instance.aplicacao
        ):
            self.add_error("marca", "Selecione a marca para informar o modelo.")
        elif marca and modelo and self.catalogo.get(marca) and modelo not in self.catalogo[marca]:
            self.add_error("aplicacao", "Este modelo não pertence à marca selecionada.")
        return data


class PecaEdicaoForm(EstiloForm, PecaAdminForm):
    motivo = forms.CharField(label="Motivo do ajuste de quantidade", max_length=240, required=False,
        help_text="Preencha quando mudar o saldo: entrada de peças, contagem, correção etc.")

    class Meta(PecaAdminForm.Meta):
        fields = ["quantidade", "status", "motivo", "nome", "marca", "aplicacao", "categoria",
            "veiculo_origem", "localizacao", "custo", "preco_venda", "ano_inicial", "ano_final",
            "motor", "posicao", "condicao", "observacoes", "versao_estoque"]
        labels = {"quantidade": "Quantidade total em estoque"}
        help_texts = {"quantidade": "Informe o total que você tem agora, não apenas a quantidade que está entrando.",
            "status": "Para saldo zero, use Baixada / indisponível. Ao repor uma peça vendida, selecione Disponível."}

    def clean(self):
        data = super().clean()
        if "quantidade" in self.changed_data and not data.get("motivo", "").strip():
            self.add_error("motivo", "Informe o motivo da alteração da quantidade.")
        return data
