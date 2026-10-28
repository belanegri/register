import re
from django import forms
from core.forms import EstiloForm
from .models import Cliente


class ClienteForm(EstiloForm, forms.ModelForm):
    cep=forms.CharField(required=False,max_length=10,label="CEP")
    inscricao_estadual=forms.CharField(required=False,max_length=20,label="Inscrição estadual")
    class Meta:
        model=Cliente
        fields=['eh_cliente','eh_fornecedor','eh_transportadora','nome','nome_fantasia','documento','ativo',
            'contato','telefone','whatsapp','email','email_financeiro','indicador_ie','inscricao_estadual',
            'cep','logradouro','numero','complemento','bairro','municipio','uf','municipio_ibge','rntrc','observacoes','endereco']
        labels={'nome':'Nome completo / razão social','endereco':'Endereço anterior / referência'}
        help_texts={'documento':'CPF com 11 ou CNPJ com 14 dígitos. A pontuação é removida ao salvar.',
            'municipio_ibge':'Usado na emissão fiscal. Preenchido também pela busca do CEP.',
            'endereco':'Preservado dos cadastros antigos. Prefira o endereço estruturado acima.'}

    def clean_documento(self):
        v=re.sub(r'[.\s/()-]','',self.cleaned_data.get('documento',''))
        if v and not re.fullmatch(r'(?:[0-9]{11}|[0-9]{14})',v):raise forms.ValidationError('Informe CPF com 11 ou CNPJ com 14 dígitos.')
        if v and not self.instance.pk and Cliente.objects.filter(documento=v).exists():
            raise forms.ValidationError('Já existe um cadastro com este CPF/CNPJ. Abra o cadastro existente e acrescente o perfil desejado.')
        return v

    def clean_cep(self):
        v=re.sub(r'[.\s-]','',self.cleaned_data.get('cep',''))
        if v and not re.fullmatch(r'[0-9]{8}',v):raise forms.ValidationError('Informe os 8 dígitos do CEP.')
        return v

    def clean_municipio_ibge(self):
        v=self.cleaned_data.get('municipio_ibge','')
        if v and not re.fullmatch(r'[0-9]{7}',v):raise forms.ValidationError('Informe o código IBGE com 7 dígitos.')
        return v

    def clean(self):
        d=super().clean()
        if not any(d.get(k) for k in ('eh_cliente','eh_fornecedor','eh_transportadora')):
            self.add_error('eh_cliente','Selecione ao menos um perfil para este cadastro.')
        ie=re.sub(r'[.\s/-]','',d.get('inscricao_estadual',''))
        if ie.upper()=='ISENTO' and d.get('indicador_ie')=='2':ie=''
        if ie and not re.fullmatch(r'[0-9]{2,14}',ie):self.add_error('inscricao_estadual','Use de 2 a 14 dígitos. Para isento, selecione a situação e deixe a IE vazia.')
        d['inscricao_estadual']=ie
        return d

    def save(self,commit=True):
        obj=super().save(commit=False)
        if obj.logradouro:obj.endereco=obj.endereco_completo
        if commit:obj.save()
        return obj

    @property
    def secoes(self):
        grupos=[('Identificação','Dados principais da pessoa ou empresa.','nome nome_fantasia documento ativo'),
            ('Contato','Canais para atendimento, compras e financeiro.','contato telefone whatsapp email email_financeiro'),
            ('Endereço fiscal','Utilizado para preencher as notas fiscais.','cep logradouro numero complemento bairro municipio uf municipio_ibge'),
            ('Dados fiscais e transporte','Situação tributária e registro do transportador, quando houver.','indicador_ie inscricao_estadual rntrc'),
            ('Informações internas','Anotações e referências do cadastro.','observacoes endereco')]
        return [dict(titulo=t,descricao=d,campos=[self[n] for n in nomes.split()]) for t,d,nomes in grupos]
