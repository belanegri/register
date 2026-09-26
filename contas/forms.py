from django import forms
from django.utils import timezone
from core.forms import EstiloForm
from vendas.models import FormaPagamento
from .models import ContaPagar

def validar_comprovante(arquivo):
    if not arquivo:
        return arquivo
    from pathlib import Path
    from PIL import Image
    if arquivo.size > 10 * 1024 * 1024:
        raise forms.ValidationError("O comprovante deve ter até 10 MB.")
    ext = Path(arquivo.name).suffix.lower()
    try:
        if ext == ".pdf":
            if not arquivo.read(5) == b"%PDF-":
                raise ValueError()
        elif ext in [".jpg", ".jpeg", ".png"]:
            imagem = Image.open(arquivo)
            if imagem.format not in ["JPEG", "PNG"]:
                raise ValueError()
            imagem.verify()
        else:
            raise ValueError()
    except Exception:
        raise forms.ValidationError("Envie um comprovante em PDF, JPG ou PNG válido.")
    finally:
        arquivo.seek(0)
    return arquivo


class CamposAnexo(forms.Form):
    comprovante = forms.FileField(label="Anexar comprovante", required=False, validators=[validar_comprovante], help_text="PDF, JPG ou PNG, até 10 MB. Você pode adicionar mais comprovantes na página da conta.")
    link_acesso = forms.URLField(label="Link de acesso", required=False, max_length=2000, widget=forms.URLInput(attrs={"placeholder":"https://"}))

    def clean_link_acesso(self):
        link = self.cleaned_data.get("link_acesso", "")
        if link and not link.lower().startswith(("https://", "http://")):
            raise forms.ValidationError("Use um link iniciado por https:// ou http://.")
        return link


class AnexoForm(EstiloForm, CamposAnexo):
    def clean(self):
        dados = super().clean()
        if not dados.get("comprovante") and not dados.get("link_acesso"):
            raise forms.ValidationError("Selecione um comprovante ou informe um link.")
        return dados


class ContaForm(EstiloForm, CamposAnexo, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].required = True
        self.fields["tipo_conta"].required = True
        self.fields["forma_prevista"].queryset = FormaPagamento.objects.filter(ativa=True, promissoria=False)
        self.fields["forma_prevista"].required = True

    class Meta:
        model = ContaPagar
        fields = ["fornecedor", "tipo_conta", "categoria", "valor", "vencimento", "forma_prevista", "data_programada", "pix_copia_cola", "observacoes"]
        widgets = {campo: forms.DateInput(attrs={"type":"date"}, format="%Y-%m-%d") for campo in ["vencimento", "data_programada"]}
        localized_fields = ["valor"]

class PagamentoForm(EstiloForm, forms.Form):
    data = forms.DateField(label="Data do pagamento", initial=timezone.localdate, widget=forms.DateInput(attrs={"type":"date"}, format="%Y-%m-%d"))
    forma = forms.ModelChoiceField(label="Forma de pagamento", queryset=FormaPagamento.objects.filter(ativa=True, promissoria=False))
    origem = forms.ChoiceField(label="Origem do pagamento", choices=[("externo","Pago fora do caixa do sistema"),("caixa","Retirar dinheiro do meu caixa aberto")])

    def clean_data(self):
        data = self.cleaned_data["data"]
        if data > timezone.localdate():
            raise forms.ValidationError("A data do pagamento não pode estar no futuro.")
        return data

    def clean(self):
        dados = super().clean()
        if dados.get("origem") == "caixa" and dados.get("forma"):
            if not dados["forma"].dinheiro:
                raise forms.ValidationError("Retirada do caixa exige pagamento em dinheiro.")
            if dados.get("data") != timezone.localdate():
                raise forms.ValidationError("Retiradas do caixa devem ser registradas na data de hoje.")
        return dados

class CancelamentoForm(EstiloForm, forms.Form):
    motivo = forms.CharField(max_length=1000, widget=forms.Textarea)


class FiltroContaForm(EstiloForm, forms.Form):
    status = forms.ChoiceField(label="Situação", choices=[("pendente","Pendentes"),("atrasada","Vencidas"),("paga","Pagas"),("cancelada","Canceladas"),("todas","Todas")])
    tipo_conta = forms.ChoiceField(label="Tipo de conta", required=False, choices=[("","Todos"),("residencial","Residencial"),("empresa","Empresa")])
    data_referencia = forms.ChoiceField(label="Datas de", choices=[("vencimento","Vencimento"),("data_programada","Pagamento programado"),("pago_em","Pagamento realizado")])
    inicio = forms.DateField(label="De", required=False, widget=forms.DateInput(attrs={"type":"date"}))
    fim = forms.DateField(label="Até", required=False, widget=forms.DateInput(attrs={"type":"date"}))

    def clean(self):
        dados = super().clean()
        if dados.get("inicio") and dados.get("fim") and dados["inicio"] > dados["fim"]:
            raise forms.ValidationError("A data inicial deve ser anterior ou igual à final.")
        return dados


class EditarAnexoForm(EstiloForm, CamposAnexo):
    remover_arquivo = forms.BooleanField(label="Excluir o arquivo atual", required=False)

    def __init__(self, *args, anexo, **kwargs):
        self.anexo = anexo
        super().__init__(*args, **kwargs)
        self.fields["comprovante"].label = "Substituir arquivo"
        self.fields["comprovante"].help_text = "Deixe vazio para manter o arquivo atual. PDF, JPG ou PNG, até 10 MB."
        self.fields["link_acesso"].help_text = "Apague este campo para excluir somente o link."
        if not anexo.arquivo:
            self.fields.pop("remover_arquivo")

    def clean(self):
        dados = super().clean()
        if dados.get("remover_arquivo") and dados.get("comprovante"):
            raise forms.ValidationError("Escolha substituir ou excluir o arquivo, não ambos.")
        mantem_arquivo = self.anexo.arquivo and not dados.get("remover_arquivo")
        if not mantem_arquivo and not dados.get("comprovante") and not dados.get("link_acesso"):
            raise forms.ValidationError("Mantenha um arquivo ou link. Para remover tudo, use Excluir anexo.")
        return dados
