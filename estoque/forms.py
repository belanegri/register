import json
import re

from django import forms
from veiculos.marcas import MARCAS, ALIASES, opcoes_marca
from veiculos.models import ModeloVeiculo
from .models import Peca
from core.forms import EstiloForm
from mercadolivre.atributos import CARACTERISTICAS_PREPARACAO, CAMPOS_CARACTERISTICAS, CaracteristicaField


class IntervaloCodigoForm(forms.Form):
    codigo_inicial = forms.CharField(label="Código inicial", required=False, max_length=40)
    codigo_final = forms.CharField(label="Código final", required=False, max_length=40)

    def clean(self):
        dados = super().clean()
        for campo in ("codigo_inicial", "codigo_final"):
            valor = dados.get(campo, "").strip().upper()
            if valor:
                numero = re.fullmatch(r"(?:REG)?([0-9]{1,37})", valor)
                if not numero:
                    self.add_error(campo, "Informe o código da peça ou somente o número.")
                    continue
                valor = "REG" + numero.group(1).zfill(6)
            dados[campo] = valor
        inicio, fim = dados.get("codigo_inicial"), dados.get("codigo_final")
        if not self.errors and inicio and fim and int(inicio[3:]) > int(fim[3:]):
            self.add_error("codigo_final", "O código final deve ser igual ou maior que o inicial.")
        return dados


class PecaAdminForm(forms.ModelForm):
    for _atributo in CARACTERISTICAS_PREPARACAO:
        locals()["ml_attr_" + _atributo["id"]] = CaracteristicaField(_atributo, required=False)

    ml_sku = forms.CharField(label="Código de identificação (SKU)", required=False, disabled=True,
        help_text="Preenchido automaticamente com o código desta peça no estoque.")
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

    class Meta:
        model = Peca
        fields = "__all__"

    class Media:
        js = ["js/veiculo-form.js", "js/ml-caracteristicas.js"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for nome in ("ml_retirada", "ml_frete_gratis"):
            if nome in self.fields:
                self.fields[nome].widget.choices = [("unknown", "Definir na publicação"), ("true", "Sim"), ("false", "Não")]
        if "ml_descricao" in self.fields:
            self.fields["ml_descricao"].widget.attrs["rows"] = 4

        if self.instance.pk:
            self.fields["versao_estoque"].initial = (
                self.instance.atualizado_em.isoformat()
            )

        self.initial["ml_sku"] = self.instance.codigo or "Gerado automaticamente ao salvar a peça"
        for nome in ("ml_caracteristicas", "ml_origem", "ml_oem"):
            if nome in self.fields:
                self.fields[nome].widget = forms.HiddenInput()
                self.fields[nome].disabled = nome == "ml_caracteristicas"
        salvas = self.instance.ml_caracteristicas or {}
        for atributo in CARACTERISTICAS_PREPARACAO:
            nome = "ml_attr_" + atributo["id"]
            self.fields[nome] = CaracteristicaField(atributo, required=False)
            valor = salvas.get(atributo["id"])
            if not valor and atributo["id"] in ("ORIGIN", "OEM"):
                antigo = getattr(self.instance, "ml_origem" if atributo["id"] == "ORIGIN" else "ml_oem")
                valor = {"value_name": antigo} if antigo else None
            self.initial[nome] = valor
        catalogo = {marca: [] for marca in MARCAS}

        for marca, modelo in ModeloVeiculo.objects.values_list("marca", "nome"):
            marca = ALIASES.get(marca, marca)
            catalogo.setdefault(marca, [])

            if modelo not in catalogo[marca]:
                catalogo[marca].append(modelo)

        if self.instance.pk and (self.instance.marca or self.instance.aplicacao):
            modelos = catalogo.setdefault(self.instance.marca, [])

            if (
                self.instance.aplicacao
                and self.instance.aplicacao not in modelos
            ):
                modelos.append(self.instance.aplicacao)

        for modelos in catalogo.values():
            modelos.sort(key=str.casefold)

        self.catalogo = catalogo

        self.fields["marca"].choices = opcoes_marca(
            self.instance.marca,
            catalogo
        )

        self.fields["marca"].widget.attrs.update({
            "data-modelos": json.dumps(
                catalogo,
                ensure_ascii=False
            ),
            "data-modelo-campo": self["aplicacao"].auto_id,
            "data-modelo-maxlength": "200",
        })

        self.fields["aplicacao"].widget.choices = [
            ("", "Selecione o modelo")
        ] + [
            (
                marca,
                [(modelo, modelo) for modelo in modelos]
            )
            for marca, modelos in catalogo.items()
        ]

        self.fields["aplicacao"].help_text = (
            "Escolha o modelo correspondente Ã  marca."
        )

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
                    "Esta peça foi alterada por outra operaÃ§Ã£o. "
                    "Recarregue a pÃ¡gina antes de salvar."
                )

        marca = data.get("marca")
        modelo = data.get("aplicacao")

        if modelo and not marca and not (
            self.instance.pk
            and not self.instance.marca
            and modelo == self.instance.aplicacao
        ):
            self.add_error(
                "marca",
                "Selecione a marca para informar o modelo."
            )

        elif (
            marca
            and modelo
            and self.catalogo.get(marca)
            and modelo not in self.catalogo[marca]
        ):
            self.add_error(
                "aplicacao",
                "Este modelo não pertence Ã  marca selecionada."
            )

        tipo = data.get("ml_garantia_tipo")
        prazo = data.get("ml_garantia_prazo")
        if tipo in ("2230280", "2230279"):
            if not prazo:
                self.add_error("ml_garantia_prazo", "Informe o prazo da garantia.")
            if not data.get("ml_garantia_unidade"):
                self.add_error("ml_garantia_unidade", "Selecione a unidade do prazo.")
        elif prazo and not tipo:
            self.add_error("ml_garantia_tipo", "Selecione o tipo de garantia.")
        if tipo == "6150835":
            data["ml_garantia_prazo"] = None
        return data

    def save(self, commit=True):
        peca = super().save(commit=False)
        if any(campo in self.data for campo in ("ncm", "origem_fiscal", "cest", "classificacao_fiscal_conferida")):
            peca.classificacao_fiscal_no_estoque = True
        salvas = dict(peca.ml_caracteristicas or {})
        for atributo in CARACTERISTICAS_PREPARACAO:
            nome = "ml_attr_" + atributo["id"]
            enviado = any(chave == nome or chave.startswith(nome + "_") for chave in self.data)
            if not enviado:
                continue
            valor = self.cleaned_data.get(nome)
            if valor:
                salvas[atributo["id"]] = valor
            else:
                salvas.pop(atributo["id"], None)
        peca.ml_caracteristicas = salvas
        for atributo, campo in (("ORIGIN", "ml_origem"), ("OEM", "ml_oem")):
            nome = "ml_attr_" + atributo
            if any(chave == nome or chave.startswith(nome + "_") for chave in self.data):
                setattr(peca, campo, salvas.get(atributo, {}).get("value_name") or "")
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
            "motor", "posicao", "compativel", "postada_online", "condicao", "observacoes", "ncm", "origem_fiscal", "cest", "classificacao_fiscal_conferida", "versao_estoque"] + ["ml_sku"] + list(Peca.CAMPOS_MERCADO_LIVRE) + list(CAMPOS_CARACTERISTICAS)
        labels = {"quantidade": "Quantidade total em estoque"}
        help_texts = {"quantidade": "Informe o total que você tem agora, não apenas a quantidade que está entrando.",
            "status": "Para saldo zero, use Baixada / indisponível. Ao repor uma peça vendida, selecione DisponÃ­vel."}

    def clean(self):
        data = super().clean()
        if "quantidade" in self.changed_data and not data.get("motivo", "").strip():
            self.add_error("motivo", "Informe o motivo da alteração da quantidade.")
        return data

    @property
    def campos_estoque(self):
        return [field for field in self.visible_fields() if field.name not in (*Peca.CAMPOS_MERCADO_LIVRE, "ml_sku", *CAMPOS_CARACTERISTICAS, "ncm", "origem_fiscal", "cest", "classificacao_fiscal_conferida")]

    @property
    def campos_fiscais(self):
        return [self[nome] for nome in ("ncm", "origem_fiscal", "cest", "classificacao_fiscal_conferida")]

    @property
    def campos_mercadolivre(self):
        return [self[nome] for nome in ("ml_sku", *Peca.CAMPOS_MERCADO_LIVRE) if not self[nome].is_hidden]

    @property
    def campos_caracteristicas(self):
        return [self[nome] for nome in CAMPOS_CARACTERISTICAS]


    @property
    def secoes_edicao(self):
        grupos=[('dados-peca','Dados da peça','Identificação e condição do produto.','nome categoria marca condicao',False),
            ('aplicacao-peca','Aplicação e compatibilidade','Veículo de origem, modelos compatíveis e características.','veiculo_origem aplicacao ano_inicial ano_final motor posicao compativel',True),
            ('estoque-peca','Estoque e valores','Saldo disponível, localização e preços.','quantidade status localizacao custo preco_venda motivo postada_online',False),
            ('classificacao-fiscal','Classificação fiscal','Dados utilizados nas notas de entrada e saída.','ncm origem_fiscal cest classificacao_fiscal_conferida',True),
            ('observacoes-peca','Observações internas','Informações para a equipe e cuidados com a peça.','observacoes',True)]
        return [dict(id=i,titulo=t,descricao=d,campos=[self[n] for n in nomes.split()],recolhivel=recolhivel,
            erros=any(self[n].errors for n in nomes.split())) for i,t,d,nomes,recolhivel in grupos]

    @property
    def erros_mercadolivre(self):
        return any(f.errors for f in [*self.campos_mercadolivre,*self.campos_caracteristicas])
