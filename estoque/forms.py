import json

from django import forms
from veiculos.marcas import MARCAS, ALIASES, opcoes_marca
from veiculos.models import ModeloVeiculo
from .models import Peca
from core.forms import EstiloForm


class PecaAdminForm(forms.ModelForm):
    NOVA_MARCA = "__nova_marca__"
    NOVO_MODELO = "__novo_modelo__"

    versao_estoque = forms.CharField(
        required=False,
        widget=forms.HiddenInput
    )

    marca = forms.ChoiceField(
        label="Marca",
        required=False
    )

    aplicacao = forms.CharField(
        label="Modelo / aplicação",
        required=False,
        max_length=200,
        widget=forms.Select
    )

    nova_marca = forms.CharField(
        label="Nova marca",
        required=False,
        max_length=80,
        widget=forms.TextInput(
            attrs={"placeholder": "Digite a nova marca"}
        )
    )

    novo_modelo = forms.CharField(
        label="Novo modelo",
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={"placeholder": "Digite o novo modelo"}
        )
    )

    class Meta:
        model = Peca
        fields = "__all__"

    class Media:
        js = ["js/veiculo-form.js"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.fields["versao_estoque"].initial = (
                self.instance.atualizado_em.isoformat()
            )

        catalogo = {marca: [] for marca in MARCAS}

        for marca, modelo in ModeloVeiculo.objects.values_list(
            "marca", "nome"
        ):
            marca = ALIASES.get(marca, marca)
            catalogo.setdefault(marca, [])

            if modelo not in catalogo[marca]:
                catalogo[marca].append(modelo)

        if self.instance.pk and self.instance.marca:
            catalogo.setdefault(self.instance.marca, [])

            if (
                self.instance.aplicacao
                and self.instance.aplicacao
                not in catalogo[self.instance.marca]
            ):
                catalogo[self.instance.marca].append(
                    self.instance.aplicacao
                )

        for modelos in catalogo.values():
            modelos.sort(key=str.casefold)

        self.catalogo = catalogo

        opcoes = list(
            opcoes_marca(self.instance.marca, catalogo)
        )

        opcoes.append(
            (self.NOVA_MARCA, "+ Nova marca")
        )

        self.fields["marca"].choices = opcoes

        self.fields["marca"].widget.attrs.update({
            "data-modelos": json.dumps(
                catalogo,
                ensure_ascii=False
            ),
            "data-modelo-campo": self["aplicacao"].auto_id,
            "data-modelo-maxlength": "200",
            "data-nova-marca": self.NOVA_MARCA,
            "data-novo-modelo": self.NOVO_MODELO,
            "data-nova-marca-campo": self["nova_marca"].auto_id,
            "data-novo-modelo-campo": self["novo_modelo"].auto_id,
        })

        self.fields["aplicacao"].widget.choices = [
            ("", "Selecione o modelo")
        ] + [
            (
                marca,
                [(modelo, modelo) for modelo in modelos]
                + [(self.NOVO_MODELO, "+ Novo modelo")]
            )
            for marca, modelos in catalogo.items()
        ]

        self.fields["aplicacao"].help_text = (
            "Escolha um modelo existente ou selecione "
            "'+ Novo modelo'."
        )

        self.fields["nova_marca"].widget.attrs["hidden"] = True
        self.fields["novo_modelo"].widget.attrs["hidden"] = True

    def clean(self):
        data = super().clean()

        if self.instance.pk:
            atual = Peca.objects.select_for_update().get(
                pk=self.instance.pk
            )

            if (
                data.get("versao_estoque")
                != atual.atualizado_em.isoformat()
            ):
                raise forms.ValidationError(
                    "Esta peça foi alterada por outra operação. "
                    "Recarregue a página antes de salvar."
                )

        marca = data.get("marca")
        modelo = data.get("aplicacao")
        nova_marca = (data.get("nova_marca") or "").strip()
        novo_modelo = (data.get("novo_modelo") or "").strip()

        if marca == self.NOVA_MARCA:
            if not nova_marca:
                self.add_error(
                    "nova_marca",
                    "Informe o nome da nova marca."
                )
            else:
                marca = nova_marca

        if modelo == self.NOVO_MODELO:
            if not novo_modelo:
                self.add_error(
                    "novo_modelo",
                    "Informe o nome do novo modelo."
                )
            else:
                modelo = novo_modelo

        if marca and not modelo:
            self.add_error(
                "aplicacao",
                "Selecione ou informe o modelo."
            )

        if modelo and not marca:
            self.add_error(
                "marca",
                "Selecione ou informe a marca."
            )

        data["marca"] = marca
        data["aplicacao"] = modelo

        return data

    def save(self, commit=True):
        peca = super().save(commit=False)

        marca = (self.cleaned_data.get("marca") or "").strip()
        modelo = (self.cleaned_data.get("aplicacao") or "").strip()

        peca.marca = marca
        peca.aplicacao = modelo

        if marca and modelo:
            ModeloVeiculo.objects.get_or_create(
                marca=marca,
                nome=modelo
            )

        if commit:
            peca.save()
            self.save_m2m()

        return peca

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
