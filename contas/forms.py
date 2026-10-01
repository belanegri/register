from django import forms
from django.utils import timezone
from core.forms import EstiloForm
from vendas.models import FormaPagamento
from .models import ContaPagar
from decimal import Decimal
from .boleto import processar_boleto, BoletoInvalido
from .pix import processar_pix, PixInvalido
import uuid


def validar_comprovante(arquivo):
    if not arquivo:
        return arquivo

    from pathlib import Path
    from PIL import Image

    if arquivo.size > 10 * 1024 * 1024:
        raise forms.ValidationError(
            "O comprovante deve ter até 10 MB."
        )

    ext = Path(arquivo.name).suffix.lower()

    try:
        if ext == ".pdf":
            if arquivo.read(5) != b"%PDF-":
                raise ValueError()

        elif ext in [".jpg", ".jpeg", ".png"]:
            imagem = Image.open(arquivo)

            if imagem.format not in ["JPEG", "PNG"]:
                raise ValueError()

            imagem.verify()

        else:
            raise ValueError()

    except Exception:
        raise forms.ValidationError(
            "Envie um comprovante em PDF, JPG ou PNG válido."
        )

    finally:
        arquivo.seek(0)

    return arquivo


class CamposAnexo(forms.Form):
    comprovante = forms.FileField(
        label="Anexar comprovante",
        required=False,
        validators=[validar_comprovante],
        help_text=(
            "PDF, JPG ou PNG, até 10 MB. "
            "Você pode adicionar mais comprovantes na página da conta."
        ),
    )

    link_acesso = forms.URLField(
        label="Link de acesso",
        required=False,
        max_length=2000,
        widget=forms.URLInput(
            attrs={"placeholder": "https://"}
        ),
    )

    def clean_link_acesso(self):
        link = self.cleaned_data.get("link_acesso", "")

        if link and not link.lower().startswith(
            ("https://", "http://")
        ):
            raise forms.ValidationError(
                "Use um link iniciado por https:// ou http://."
            )

        return link


class AnexoForm(EstiloForm, CamposAnexo):
    from .models import AnexoConta

    tipo = forms.ChoiceField(
        label="Tipo do documento",
        choices=AnexoConta.TIPOS,
        initial="cobranca",
        required=False,
    )

    def clean(self):
        dados = super().clean()

        if not dados.get("comprovante") and not dados.get(
            "link_acesso"
        ):
            raise forms.ValidationError(
                "Selecione um comprovante ou informe um link."
            )

        return dados

class ArquivosWidget(forms.ClearableFileInput):
    allow_multiple_selected = True


class ArquivosField(forms.FileField):
    def clean(self, data, initial=None):
        arquivos = (
            data
            if isinstance(data, (list, tuple))
            else ([data] if data else [])
        )

        if len(arquivos) > 10:
            raise forms.ValidationError(
                "Selecione no máximo 10 documentos por vez."
            )

        return [
            super(ArquivosField, self).clean(
                arquivo, initial
            )
            for arquivo in arquivos
        ]


class ContaForm(EstiloForm, CamposAnexo, forms.ModelForm):
    chave = forms.UUIDField(
        initial=uuid.uuid4,
        widget=forms.HiddenInput,
    )

    codigo_boleto = forms.CharField(
        label="Código de barras / Linha digitável",
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "placeholder": (
                    "Passe o leitor ou cole a linha digitável"
                ),
                "autocomplete": "off",
                "inputmode": "numeric",
                "data-codigo-boleto": "true",
            }
        ),
    )

    ciclo_boleto = forms.ChoiceField(
        label="Ciclo do vencimento do boleto", required=False, initial="atual",
        choices=[("atual", "Atual (desde 22/02/2025)"), ("anterior", "Anterior (até 21/02/2025)")],
        help_text="Para boletos antigos, selecione o ciclo anterior. Confira a data no documento.",
    )

    competencia = forms.DateField(
        label="Competência (mês/ano)",
        required=False,
        input_formats=["%Y-%m"],
        widget=forms.DateInput(
            attrs={"type": "month"},
            format="%Y-%m",
        ),
    )

    quantidade_lancamentos = forms.IntegerField(
        label="Quantidade de lançamentos / parcelas",
        min_value=2,
        max_value=120,
        required=False,
    )

    documentos = ArquivosField(
        label="Documentos da cobrança",
        required=False,
        widget=ArquivosWidget(
            attrs={
                "accept": ".pdf,.jpg,.jpeg,.png"
            }
        ),
        validators=[validar_comprovante],
        help_text=(
            "Até 10 arquivos em PDF, JPG ou PNG, "
            "com até 10 MB cada. Não registra pagamento."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Recupera o código salvo ao editar uma conta.
        if self.instance.pk:
            self.fields["codigo_boleto"].initial = (
                self.instance.linha_digitavel
                or self.instance.codigo_barras
                or ""
            )

        if self.instance.pk and self.fields['codigo_boleto'].initial:
            try:
                anterior = processar_boleto(self.fields['codigo_boleto'].initial, 'anterior')
                if anterior['vencimento'] and self.instance.vencimento == anterior['vencimento']:
                    self.initial.setdefault('ciclo_boleto', 'anterior')
            except BoletoInvalido:
                pass

        self.fields["descricao"].required = True

        self.fields["valor_original"].required = True
        self.fields["valor_original"].min_value = Decimal(
            "0.01"
        )

        for nome in [
            "valor_original",
            "desconto",
            "juros",
            "multa",
            "acrescimos",
        ]:
            self.fields[nome].widget.attrs.update(
                {
                    "inputmode": "decimal",
                    "data-valor-conta": nome,
                }
            )

            if nome != "valor_original":
                self.fields[nome].required = False

        self.fields["categoria"].required = True
        self.fields["tipo_conta"].required = True

        self.fields["forma_prevista"].queryset = (
            FormaPagamento.objects.filter(
                ativa=True,
                promissoria=False,
            )
        )

        self.fields["forma_prevista"].required = False

        if not self.instance.pk:
            self.initial.setdefault(
                "modo", "unica"
            )

        else:
            self.fields["chave"].required = False

            for nome in [
                "modo",
                "frequencia",
                "quantidade_lancamentos",
            ]:
                self.fields[nome].disabled = True

            self.initial[
                "quantidade_lancamentos"
            ] = (
                self.instance.total_parcelas
                if self.instance.total_parcelas > 1
                else None
            )

        if (
            self.instance.pk
            and self.instance.valor_pago
        ):
            for nome in [
                "valor_original",
                "desconto",
                "juros",
                "multa",
                "acrescimos",
            ]:
                self.fields[nome].disabled = True

        for nome in [
            "observacoes",
            "pix_copia_cola",
        ]:
            self.fields[nome].widget.attrs[
                "rows"
            ] = 3

        if self.is_bound:
            self.data = self.data.copy()
            try:
                boleto = processar_boleto(self.data.get(self.add_prefix('codigo_boleto')), self.data.get(self.add_prefix('ciclo_boleto')) or 'atual')
            except BoletoInvalido:
                pass  # O erro será associado ao campo em clean().
            else:
                for campo, valor in [('valor_original', boleto['valor']), ('vencimento', boleto['vencimento'])]:
                    chave = self.add_prefix(campo)
                    if valor is not None and not self.data.get(chave) and not self.fields[campo].disabled:
                        self.data[chave] = str(valor)

    def clean(self):
        dados = super().clean()
        dados['codigo_barras'] = dados['linha_digitavel'] = ''
        pix = dados.get('pix_copia_cola', '')
        if pix.startswith('000201') and pix != self.instance.pix_copia_cola:
            try:
                dados['pix_copia_cola'] = processar_pix(pix)['pix_copia_cola']
            except PixInvalido as exc:
                self.add_error('pix_copia_cola', str(exc))
        if dados.get('codigo_boleto'):
            try:
                boleto = processar_boleto(dados['codigo_boleto'], dados.get('ciclo_boleto') or 'atual')
                if not self.instance.pk and dados.get('modo') == 'parcelada':
                    raise BoletoInvalido('Gere as parcelas sem código e informe o boleto de cada parcela na edição.')
                for campo in ['codigo_barras', 'linha_digitavel']:
                    dados[campo] = boleto[campo]
            except BoletoInvalido as exc:
                self.add_error('codigo_boleto', str(exc))
        for campo in ['codigo_barras', 'linha_digitavel']:
            setattr(self.instance, campo, dados[campo])


        for nome in [
            "desconto",
            "juros",
            "multa",
            "acrescimos",
        ]:
            dados[nome] = (
                dados.get(nome)
                or Decimal("0")
            )

        valores = [
            dados.get(nome)
            for nome in [
                "valor_original",
                "desconto",
                "juros",
                "multa",
                "acrescimos",
            ]
        ]

        if all(
            valor is not None
            for valor in valores
        ):
            (
                original,
                desconto,
                juros,
                multa,
                acrescimos,
            ) = valores

            if (
                original <= 0
                or any(
                    v < 0
                    for v in valores[1:]
                )
            ):
                raise forms.ValidationError(
                    "Informe um valor original positivo "
                    "e ajustes não negativos."
                )

            total = (
                original
                - desconto
                + juros
                + multa
                + acrescimos
            )

            if (
                total <= 0
                or total > Decimal(
                    "9999999999.99"
                )
            ):
                raise forms.ValidationError(
                    "O valor total deve ser positivo "
                    "e não pode ultrapassar "
                    "R$ 9.999.999.999,99."
                )

            self.instance.valor = total

            if (
                self.instance.valor_pago
                > total
            ):
                raise forms.ValidationError(
                    "O total não pode ser inferior "
                    "ao valor já pago."
                )

            if (
                not self.instance.pk
                and dados.get("modo")
                == "parcelada"
                and dados.get(
                    "quantidade_lancamentos"
                )
            ):
                if (
                    total
                    < Decimal(
                        dados[
                            "quantidade_lancamentos"
                        ]
                    ) / 100
                ):
                    raise forms.ValidationError(
                        "Cada parcela precisa ter "
                        "pelo menos R$ 0,01."
                    )

        if (
            not self.instance.pk
            and dados.get("modo")
            in [
                "recorrente",
                "parcelada",
            ]
        ):
            if not dados.get(
                "quantidade_lancamentos"
            ):
                self.add_error(
                    "quantidade_lancamentos",
                    "Informe entre 2 e 120 lançamentos.",
                )

            if (
                dados.get("modo")
                == "recorrente"
                and not dados.get(
                    "frequencia"
                )
            ):
                self.add_error(
                    "frequencia",
                    "Selecione a frequência.",
                )

        if (
            dados.get("emissao")
            and dados.get("vencimento")
            and dados["emissao"]
            > dados["vencimento"]
        ):
            self.add_error(
                "vencimento",
                "O vencimento não pode ser "
                "anterior à emissão.",
            )

        return dados

    class Meta:
        model = ContaPagar

        fields = [
            "descricao",
            "fornecedor",
            "tipo_conta",
            "categoria",
            "subcategoria",
            "centro_custo",
            "numero_documento",
            "competencia",
            "valor_original",
            "desconto",
            "juros",
            "multa",
            "acrescimos",
            "emissao",
            "vencimento",
            "forma_prevista",
            "data_programada",
            "pix_copia_cola",
            "modo",
            "frequencia",
            "observacoes",
        ]

        widgets = {
            campo: forms.DateInput(
                attrs={
                    "type": "date"
                },
                format="%Y-%m-%d",
            )
            for campo in [
                "emissao",
                "vencimento",
                "data_programada",
            ]
        }

        localized_fields = [
            "valor_original",
            "desconto",
            "juros",
            "multa",
            "acrescimos",
        ]

        labels = {
            "forma_prevista": (
                "Forma de pagamento prevista"
            ),
            "modo": (
                "Tipo de lançamento"
            ),
            "emissao": (
                "Data de emissão"
            ),
            "vencimento": (
                "Data de vencimento"
            ),
            "valor_original": (
                "Valor original (R$)"
            ),
            "desconto": (
                "Desconto (R$)"
            ),
            "juros": (
                "Juros (R$)"
            ),
            "multa": (
                "Multa (R$)"
            ),
            "acrescimos": (
                "Outros acréscimos (R$)"
            ),
        }


class PagamentoForm(EstiloForm, forms.Form):
    chave = forms.UUIDField(
        initial=uuid.uuid4,
        widget=forms.HiddenInput,
    )

    valor = forms.DecimalField(
        label="Valor pago (R$)",
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        localize=True,
    )

    juros = forms.DecimalField(
        label="Juros adicionais neste pagamento (R$)",
        min_value=0,
        max_digits=12,
        decimal_places=2,
        required=False,
        initial=0,
        localize=True,
    )

    desconto = forms.DecimalField(
        label="Desconto adicional neste pagamento (R$)",
        min_value=0,
        max_digits=12,
        decimal_places=2,
        required=False,
        initial=0,
        localize=True,
    )

    comprovante = forms.FileField(
        label="Comprovante de pagamento",
        required=False,
        validators=[validar_comprovante],
    )

    observacao = forms.CharField(
        label="Observação",
        required=False,
        max_length=2000,
        widget=forms.Textarea(
            attrs={"rows": 3}
        ),
    )

    data = forms.DateField(
        label="Data do pagamento",
        initial=timezone.localdate,
        widget=forms.DateInput(
            attrs={"type": "date"},
            format="%Y-%m-%d",
        ),
    )

    forma = forms.ModelChoiceField(
        label="Forma de pagamento",
        queryset=FormaPagamento.objects.filter(
            ativa=True,
            promissoria=False,
        ),
    )

    origem = forms.ChoiceField(
        label="Origem do pagamento",
        choices=[
            (
                "externo",
                "Pago fora do caixa do sistema",
            ),
            (
                "caixa",
                "Retirar dinheiro do meu caixa aberto",
            ),
        ],
    )

    def clean_data(self):
        data = self.cleaned_data["data"]

        if data > timezone.localdate():
            raise forms.ValidationError(
                "A data do pagamento "
                "não pode estar no futuro."
            )

        return data

    def clean(self):
        dados = super().clean()

        if (
            dados.get("origem") == "caixa"
            and dados.get("forma")
        ):
            if not dados["forma"].dinheiro:
                raise forms.ValidationError(
                    "Retirada do caixa exige "
                    "pagamento em dinheiro."
                )

            if (
                dados.get("data")
                != timezone.localdate()
            ):
                raise forms.ValidationError(
                    "Retiradas do caixa devem ser "
                    "registradas na data de hoje."
                )

        return dados


class CancelamentoForm(EstiloForm, forms.Form):
    motivo = forms.CharField(
        max_length=1000,
        widget=forms.Textarea,
    )


class FiltroContaForm(EstiloForm, forms.Form):
    status = forms.ChoiceField(
        label="Situação",
        choices=[
            ("pendente", "Em aberto"),
            ("aguardando", "Aguardando"),
            ("programada", "Programadas"),
            ("atrasada", "Atrasadas"),
            ("parcial", "Parcialmente pagas"),
            ("paga", "Pagas"),
            ("cancelada", "Canceladas"),
            ("todas", "Todas"),
        ],
    )

    tipo_conta = forms.ChoiceField(
        label="Tipo de conta",
        required=False,
        choices=[
            ("", "Todos"),
            ("residencial", "Residencial"),
            ("empresa", "Empresa"),
        ],
    )

    data_referencia = forms.ChoiceField(
        label="Datas de",
        choices=[
            ("vencimento", "Vencimento"),
            (
                "data_programada",
                "Pagamento programado",
            ),
            (
                "pago_em",
                "Pagamento realizado",
            ),
        ],
    )

    inicio = forms.DateField(
        label="De",
        required=False,
        widget=forms.DateInput(
            attrs={"type": "date"}
        ),
    )

    fim = forms.DateField(
        label="Até",
        required=False,
        widget=forms.DateInput(
            attrs={"type": "date"}
        ),
    )

    def clean(self):
        dados = super().clean()

        if (
            dados.get("inicio")
            and dados.get("fim")
            and dados["inicio"]
            > dados["fim"]
        ):
            raise forms.ValidationError(
                "A data inicial deve ser anterior "
                "ou igual à final."
            )

        return dados


class EditarAnexoForm(EstiloForm, CamposAnexo):
    remover_arquivo = forms.BooleanField(
        label="Excluir o arquivo atual",
        required=False,
    )

    def __init__(
        self,
        *args,
        anexo,
        **kwargs,
    ):
        self.anexo = anexo

        super().__init__(
            *args,
            **kwargs,
        )

        self.fields[
            "comprovante"
        ].label = "Substituir arquivo"

        self.fields[
            "comprovante"
        ].help_text = (
            "Deixe vazio para manter o arquivo atual. "
            "PDF, JPG ou PNG, até 10 MB."
        )

        self.fields[
            "link_acesso"
        ].help_text = (
            "Apague este campo para excluir "
            "somente o link."
        )

        if not anexo.arquivo:
            self.fields.pop(
                "remover_arquivo"
            )

    def clean(self):
        dados = super().clean()

        if (
            dados.get("remover_arquivo")
            and dados.get("comprovante")
        ):
            raise forms.ValidationError(
                "Escolha substituir ou excluir "
                "o arquivo, não ambos."
            )

        mantem_arquivo = (
            self.anexo.arquivo
            and not dados.get(
                "remover_arquivo"
            )
        )

        if (
            not mantem_arquivo
            and not dados.get(
                "comprovante"
            )
            and not dados.get(
                "link_acesso"
            )
        ):
            raise forms.ValidationError(
                "Mantenha um arquivo ou link. "
                "Para remover tudo, use Excluir anexo."
            )

        return dados
