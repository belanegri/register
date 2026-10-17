from django import forms
from estoque.models import Peca
from decimal import Decimal


class VinculoForm(forms.Form):
    codigo = forms.CharField(label="Código exato da peça no REGISTER", max_length=40,
                             widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "REG000001"}))

    def clean_codigo(self):
        try:
            self.peca = Peca.objects.get(codigo__iexact=self.cleaned_data["codigo"].strip())
        except Peca.DoesNotExist:
            raise forms.ValidationError("Nenhuma peça desta loja possui esse código.") from None
        return self.peca.codigo


class PublicacaoForm(forms.Form):
    titulo = forms.CharField(label="Título / nome do produto", max_length=60)
    preco = forms.DecimalField(label="Preço no Mercado Livre (R$)", min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    quantidade = forms.IntegerField(label="Quantidade a anunciar", min_value=1)
    condicao = forms.ChoiceField(label="Condição", choices=[("used", "Usada"), ("new", "Nova"), ("not_specified", "Não especificada")])
    tipo = forms.ChoiceField(label="Tipo de anúncio")
    envio = forms.ChoiceField(label="Envio", choices=[("me2", "Mercado Envios"), ("not_specified", "Combinar com o comprador")])
    retirada = forms.BooleanField(label="Permitir retirada pessoal", required=False)
    frete_gratis = forms.BooleanField(label="Oferecer frete grátis (custos conforme regras do Mercado Livre)", required=False)
    descricao = forms.CharField(label="Descrição pública do anúncio", max_length=50000, widget=forms.Textarea(attrs={"rows": 6}))

    def __init__(self, *args, peca, categoria, atributos, tipos, **kwargs):
        super().__init__(*args, **kwargs)
        self.categoria, self.atributos = categoria, []
        self.fields["titulo"] = forms.CharField(label="Título / nome do produto",
            max_length=min(200, categoria.get("settings", {}).get("max_title_length", 60) or 60))
        self.fields["tipo"].choices = [(t["id"], t["name"]) for t in tipos if t.get("id") in ("gold_special", "gold_pro", "free")]
        self.fields["quantidade"].max_value = peca.quantidade
        self.fields["fotos"] = forms.ModelMultipleChoiceField(label="Fotos públicas do anúncio", queryset=peca.fotos.all(), widget=forms.CheckboxSelectMultiple)
        self.max_fotos = min(20, categoria.get("settings", {}).get("max_pictures_per_item", 12) or 12)
        self.estoque = peca.quantidade
        for attr in atributos:
            tags = attr.get("tags", {})
            if tags.get("read_only") or tags.get("hidden") or attr.get("id") in ("ITEM_CONDITION", "SELLER_SKU"):
                continue
            chave = "attr_" + attr["id"]
            required = bool(tags.get("required") or tags.get("catalog_required"))
            valores = attr.get("values", [])
            if valores and attr.get("value_type") == "list":
                self.fields[chave] = forms.ChoiceField(label=attr["name"], required=required,
                    choices=[("", "Selecione")] + [(v["id"], v["name"]) for v in valores if "id" in v])
            else:
                self.fields[chave] = forms.CharField(label=attr["name"], required=required, max_length=255)
            self.atributos.append((attr, chave))
        self.initial.update(titulo=peca.nome, preco=peca.preco_venda, quantidade=1,
                            condicao="new" if peca.condicao == "nova" else "used", envio="me2")
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                field.widget.attrs["class"] = "form-control"

    def clean_quantidade(self):
        n = self.cleaned_data["quantidade"]
        if n > self.estoque:
            raise forms.ValidationError("Quantidade superior ao estoque disponível.")
        return n

    def clean_titulo(self):
        titulo = self.cleaned_data["titulo"].strip()
        if len(titulo) > self.fields["titulo"].max_length:
            raise forms.ValidationError("O título excede o limite desta categoria.")
        return titulo

    def clean_fotos(self):
        fotos = self.cleaned_data["fotos"]
        if fotos.count() > self.max_fotos:
            raise forms.ValidationError(f"Esta categoria permite até {self.max_fotos} fotos.")
        return fotos

    def atributos_payload(self):
        return [{"id": a["id"], "value_id" if isinstance(self.fields[k], forms.ChoiceField) else "value_name": self.cleaned_data[k]}
                for a, k in self.atributos if self.cleaned_data.get(k)]
