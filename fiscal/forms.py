from django import forms
from django.db import transaction
from django.db.models import Max
from django.views.decorators.debug import sensitive_variables

from core.forms import EstiloForm
from .models import ConfiguracaoFiscal, ParametroProduto, ParametroServico, SequenciaFiscal, DocumentoFiscal, EventoFiscal, Modelo
from .seguranca import ErroFiscal, criptografar, salvar_a1


class ConfiguracaoForm(EstiloForm, forms.ModelForm):
    certificado_a1 = forms.FileField(required=False, label="Certificado A1 (.pfx/.p12)")
    senha_a1 = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False), label="Senha do A1")
    csc = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False), label="CSC (deixe vazio para manter)")

    class Meta:
        model = ConfiguracaoFiscal
        fields = ['ativa','ambiente','homologacao_validada','producao_validada','modelo_mercadorias',
            'cnpj','razao_social','nome_fantasia','ie','im','crt','uf','municipio_ibge','municipio',
            'logradouro','numero','bairro','cep','telefone','email','natureza_operacao','csc_id','qr_code_versao','endpoints','parametros_nfse']

    @sensitive_variables('dados','senha')
    def clean(self):
        dados = super().clean()
        for campo in ('endpoints','parametros_nfse'):
            if dados.get(campo) is None:dados[campo]={}
            elif not isinstance(dados[campo],dict):self.add_error(campo,'Informe um objeto JSON.')
        certificado = dados.get('certificado_a1'); senha = dados.get('senha_a1')
        try:
            if certificado:
                if certificado.size>1024*1024:
                    raise ErroFiscal('O certificado deve ter até 1 MB.')
                if not senha:raise ErroFiscal('Informe a senha do novo certificado A1.')
                salvar_a1(self.instance, certificado.read(), senha)
            elif senha:
                raise ErroFiscal('Envie o certificado junto com a nova senha.')
            if dados.get('csc'):
                self.instance.csc_criptografado=criptografar(dados['csc'])
                self.instance.csc_ambiente=dados.get('ambiente','homologacao')
        except ErroFiscal as erro:
            raise forms.ValidationError(str(erro)) from None
        return dados


class SolicitacaoForm(EstiloForm, forms.Form):
    venda = forms.IntegerField(required=False,min_value=1,label="Número interno da venda")
    ordem_servico = forms.IntegerField(required=False,min_value=1,label="Número interno da OS")
    modelo = forms.ChoiceField(choices=[('', 'Conforme configuração')]+list(Modelo.choices),required=False)
    serie = forms.IntegerField(min_value=1,max_value=999,initial=1)
    destinatario = forms.JSONField(required=False,initial=dict,help_text="Endereço fiscal estruturado do destinatário quando necessário. Não altera o cadastro do cliente.")

    def clean(self):
        dados=super().clean()
        if bool(dados.get('venda'))==bool(dados.get('ordem_servico')):
            raise forms.ValidationError('Informe uma venda ou uma OS.')
        if dados.get('destinatario') is not None and not isinstance(dados['destinatario'],dict):
            raise forms.ValidationError('Informe o destinatário como objeto JSON.')
        return dados


class JustificativaForm(EstiloForm, forms.Form):
    justificativa = forms.CharField(min_length=15,max_length=255,widget=forms.Textarea)


class InutilizacaoForm(JustificativaForm):
    modelo=forms.ChoiceField(choices=[('55','NF-e'),('65','NFC-e')])
    serie=forms.IntegerField(min_value=1,max_value=999,initial=1)
    numero_inicial=forms.IntegerField(min_value=1,max_value=999999999)
    numero_final=forms.IntegerField(min_value=1,max_value=999999999)
    ano=forms.IntegerField(min_value=2006,max_value=9999)


class ProdutoForm(EstiloForm, forms.ModelForm):
    def clean_tributos_adicionais(self):
        dados=self.cleaned_data.get('tributos_adicionais')
        if dados is None:return {}
        if not isinstance(dados,dict):raise forms.ValidationError('Informe um objeto JSON.')
        return dados

    class Meta:
        model=ParametroProduto
        fields=['peca','ncm','cfop','origem','unidade','cest','csosn','cst_icms','aliquota_icms',
                'cst_pis','aliquota_pis','cst_cofins','aliquota_cofins','tributos_adicionais']


class ServicoForm(EstiloForm, forms.ModelForm):
    def clean_parametros(self):
        dados=self.cleaned_data.get('parametros')
        if dados is None:return {}
        if not isinstance(dados,dict):raise forms.ValidationError('Informe um objeto JSON.')
        return dados

    class Meta:
        model=ParametroServico
        fields=['servico','item_lista_lc116','codigo_tributacao_nacional','codigo_tributacao_municipal',
                'nbs','aliquota_iss','iss_retido','municipio_incidencia','parametros']


class SequenciaForm(EstiloForm, forms.ModelForm):
    class Meta:
        model=SequenciaFiscal
        fields=['modelo','ambiente','serie','proximo_numero']

    @transaction.atomic
    def save(self, commit=True):
        config=ConfiguracaoFiscal.objects.select_for_update().get(pk=1)
        sequencia=super().save(commit=False)
        atual=SequenciaFiscal.objects.select_for_update().filter(configuracao=config,modelo=sequencia.modelo,
            ambiente=sequencia.ambiente,serie=sequencia.serie).first()
        ultimo=DocumentoFiscal.objects.filter(configuracao=config,modelo=sequencia.modelo,ambiente=sequencia.ambiente,
            serie=sequencia.serie).aggregate(n=Max('numero'))['n'] or 0
        faixa=EventoFiscal.objects.filter(configuracao=config,modelo=sequencia.modelo,ambiente=sequencia.ambiente,
            serie=sequencia.serie,tipo='inutilizacao').aggregate(n=Max('numero_final'))['n'] or 0
        if sequencia.proximo_numero<=max(ultimo,faixa):
            raise ErroFiscal('A numeração deve ultrapassar todos os números reservados e faixas inutilizadas.')
        if atual:
            atual.proximo_numero=sequencia.proximo_numero;atual.save(update_fields=['proximo_numero']);return atual
        sequencia.configuracao=config
        if commit:sequencia.save()
        return sequencia
