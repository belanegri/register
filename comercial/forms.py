from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet

from core.forms import EstiloForm
from .models import Servico, Documento, ItemDocumento, ContaReceber


class ServicoForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = Servico
        fields = [
            'nome',
            'categoria',
            'descricao',
            'valor_padrao',
            'ativo',
            'observacoes',
        ]
        labels = {
            'valor_padrao': 'Valor padrão (R$)',
        }


class DocumentoForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = Documento
        fields = [
            'cliente',
            'veiculo',
            'placa',
            'ano',
            'km',
            'combustivel',
            'validade',
            'previsao',
            'conclusao',
            'responsavel',
            'relato',
            'diagnostico',
            'solicitado',
            'desconto',
            'forma_pagamento',
            'condicao_pagamento',
            'parcelas',
            'primeiro_vencimento',
            'observacoes',
            'condicoes',
            'status',
        ]

        widgets = {
            'validade': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d'
            ),
            'previsao': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d'
            ),
            'conclusao': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d'
            ),
            'primeiro_vencimento': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d'
            ),
        }

        labels = {
            'cliente': 'Cliente',
            'veiculo': 'Veículo / Marca e modelo',
            'placa': 'Placa',
            'ano': 'Ano',
            'km': 'KM',
            'combustivel': 'Combustível',
            'validade': 'Validade do orçamento',
            'previsao': 'Previsão de conclusão',
            'conclusao': 'Data de conclusão',
            'responsavel': 'Responsável / Técnico',
            'relato': 'Relato do cliente',
            'diagnostico': 'Diagnóstico',
            'solicitado': 'Serviço solicitado',
            'desconto': 'Desconto (R$)',
            'forma_pagamento': 'Forma de pagamento',
            'condicao_pagamento': 'Condição',
            'parcelas': 'Número de parcelas',
            'primeiro_vencimento': 'Primeiro vencimento',
            'observacoes': 'Observações internas',
            'condicoes': 'Condições / Informações para impressão',
            'status': 'Status',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        orcamento = self.instance.tipo == 'orcamento'

        if orcamento:
            estados = [
                'rascunho',
                'enviado',
                'aprovado',
                'recusado',
                'vencido',
            ]
        else:
            estados = [
                'aberta',
                'andamento',
                'aguardando',
                'finalizada',
                'entregue',
                'cancelada',
            ]

        self.fields['status'].choices = [
            (chave, nome)
            for chave, nome in Documento.STATUS
            if chave in estados
        ]

        if orcamento:
            campos_remover = [
                'combustivel',
                'previsao',
                'conclusao',
                'responsavel',
                'relato',
                'diagnostico',
                'solicitado',
            ]
        else:
            campos_remover = [
                'validade',
            ]

        for campo in campos_remover:
            self.fields.pop(campo)

        if orcamento:
            self.fields['validade'].required = True

        self.fields['forma_pagamento'].required = False
        self.fields['primeiro_vencimento'].required = False

        self.fields['parcelas'].widget.attrs.update({
            'min': '1',
            'max': '60',
        })

        self.fields['condicao_pagamento'].widget.attrs.update({
            'data-condicao-pagamento': 'true',
        })

        self.fields['parcelas'].widget.attrs.update({
            'data-campo-parcelas': 'true',
        })

        self.fields['primeiro_vencimento'].widget.attrs.update({
            'data-campo-vencimento': 'true',
        })

    def clean(self):
        cleaned_data = super().clean()

        condicao = cleaned_data.get('condicao_pagamento')
        parcelas = cleaned_data.get('parcelas')
        primeiro_vencimento = cleaned_data.get('primeiro_vencimento')

        if condicao == 'avista':
            cleaned_data['parcelas'] = 1
            cleaned_data['primeiro_vencimento'] = None

        elif condicao == 'parcelado':
            if not parcelas or parcelas < 2:
                self.add_error(
                    'parcelas',
                    'Informe pelo menos 2 parcelas.'
                )

            if not primeiro_vencimento:
                self.add_error(
                    'primeiro_vencimento',
                    'Informe o primeiro vencimento.'
                )

        return cleaned_data


class ItemForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = ItemDocumento
        fields = [
            'peca',
            'servico',
            'quantidade',
            'preco',
        ]

        labels = {
            'peca': 'Peça',
            'servico': 'Serviço',
            'quantidade': 'Quantidade',
            'preco': 'Valor unitário (R$)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['preco'].required = False

    def clean(self):
        data = super().clean()

        peca = data.get('peca')
        servico = data.get('servico')

        if bool(peca) == bool(servico):
            raise forms.ValidationError(
                'Selecione uma peça OU um serviço por linha.'
            )

        if servico and not servico.ativo:
            raise forms.ValidationError(
                'Serviço inativo.'
            )

        if data.get('preco') is None:
            data['preco'] = (
                peca.preco_venda
                if peca
                else servico.valor_padrao
            )

        self.instance.descricao = (
            peca.nome
            if peca
            else servico.nome
        )[:240]

        return data


class ItensBase(BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        vistos = set()
        subtotal = Decimal('0')

        for form in self.forms:
            data = form.cleaned_data

            if not data or data.get('DELETE'):
                continue

            if data.get('peca'):
                chave = ('p', data['peca'].pk)
            else:
                chave = ('s', data['servico'].pk)

            if chave in vistos:
                raise forms.ValidationError(
                    'Não repita itens; ajuste a quantidade '
                    'na linha existente.'
                )

            vistos.add(chave)

            subtotal += (
                data['quantidade']
                * data['preco']
            )

        if (
            self.instance.desconto < 0
            or self.instance.desconto >= subtotal
            or subtotal > Decimal('9999999999.99')
        ):
            raise forms.ValidationError(
                'O total deve ser positivo e o desconto '
                'menor que o subtotal.'
            )


ItensFormSet = inlineformset_factory(
    Documento,
    ItemDocumento,
    form=ItemForm,
    formset=ItensBase,
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True,
    max_num=100,
    validate_max=True,
)


class ContaForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = ContaReceber
        fields = [
            'cliente',
            'descricao',
            'valor_original',
            'vencimento',
            'observacoes',
        ]

        widgets = {
            'vencimento': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d'
            ),
        }