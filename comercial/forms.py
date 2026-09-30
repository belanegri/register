from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from core.forms import EstiloForm
from .models import Servico, Documento, ItemDocumento, ContaReceber


class ServicoForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = Servico
        fields = ['nome','categoria','descricao','valor_padrao','ativo','observacoes']
        labels = {'valor_padrao':'Valor padrão (R$)'}


class DocumentoForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = Documento
        fields = ['cliente','veiculo','placa','ano','km','combustivel','validade','previsao','conclusao','responsavel','relato','diagnostico','solicitado','desconto','observacoes','condicoes','status']
        widgets = {k:forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d') for k in ['validade','previsao','conclusao']}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        orc = self.instance.tipo == 'orcamento'
        estados = ['rascunho','enviado','aprovado','recusado','vencido'] if orc else ['aberta','andamento','aguardando','finalizada','entregue','cancelada']
        self.fields['status'].choices = [(k,v) for k,v in Documento.STATUS if k in estados]
        for campo in (['combustivel','previsao','conclusao','responsavel','relato','diagnostico','solicitado'] if orc else ['validade']):
            self.fields.pop(campo)
        if orc: self.fields['validade'].required = True


class ItemForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = ItemDocumento
        fields = ['peca','servico','quantidade','preco']
        labels = {'peca':'Peça', 'servico':'Serviço', 'quantidade':'Quantidade', 'preco':'Valor unitário (R$)'}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['preco'].required = False

    def clean(self):
        data = super().clean()
        p, s = data.get('peca'),data.get('servico')
        if bool(p) == bool(s):
            raise forms.ValidationError('Selecione uma peça OU um serviço por linha.')
        if s and not s.ativo:
            raise forms.ValidationError('Serviço inativo.')
        if data.get('preco') is None:
            data['preco'] = p.preco_venda if p else s.valor_padrao
        self.instance.descricao = (p.nome if p else s.nome)[:240]
        return data


class ItensBase(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors): return
        vistos = set()
        subtotal = Decimal('0')
        for f in self.forms:
            d = f.cleaned_data
            if not d or d.get('DELETE'): continue
            key = ('p',d['peca'].pk) if d.get('peca') else ('s',d['servico'].pk)
            if key in vistos: raise forms.ValidationError('Não repita itens; ajuste a quantidade na linha existente.')
            vistos.add(key)
            subtotal += d['quantidade'] * d['preco']
        if self.instance.desconto < 0 or self.instance.desconto >= subtotal or subtotal > Decimal('9999999999.99'):
            raise forms.ValidationError('O total deve ser positivo e o desconto menor que o subtotal.')


ItensFormSet = inlineformset_factory(Documento,ItemDocumento,form=ItemForm,formset=ItensBase,extra=0,can_delete=True,min_num=1,validate_min=True,max_num=100,validate_max=True)


class ContaForm(EstiloForm,forms.ModelForm):
    class Meta:
        model = ContaReceber
        fields = ['cliente','descricao','valor_original','vencimento','observacoes']
        widgets = {'vencimento':forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d')}
