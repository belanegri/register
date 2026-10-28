from .observacoes import ObservacaoCampos
from django.http import Http404
import re
import uuid

from django import forms
from django.db import transaction
from django.db.models import Max
from django.views.decorators.debug import sensitive_variables

from core.forms import EstiloForm
from .models import ConfiguracaoFiscal, ParametroProduto, ParametroServico, SequenciaFiscal, DocumentoFiscal, EventoFiscal, Modelo, Operacao
from .seguranca import ErroFiscal, criptografar, salvar_a1
from .transporte import TransporteCampos


class CampoNumericoFormatado(forms.CharField):
    """Remove apenas a pontuação de apresentação antes dos limites do modelo."""
    def to_python(self, value):
        return re.sub(r"[.\s/()+-]", "", super().to_python(value))


class ConfiguracaoForm(EstiloForm, forms.ModelForm):
    serie_padrao = forms.IntegerField(min_value=1,max_value=999,required=False,label="Série padrão da NF-e")

    def clean_serie_padrao(self):
        return self.cleaned_data.get('serie_padrao') or self.instance.serie_padrao or 1

    cnpj = CampoNumericoFormatado(max_length=14, label="CNPJ", widget=forms.TextInput(attrs={"maxlength": 18}), help_text="Com ou sem pontuação.")
    cep = CampoNumericoFormatado(max_length=8, label="CEP", widget=forms.TextInput(attrs={"maxlength": 9}))
    telefone = CampoNumericoFormatado(max_length=14, required=False, label="Telefone", widget=forms.TextInput(attrs={"maxlength": 22}))
    certificado_a1 = forms.FileField(required=False, label="Certificado A1 (.pfx/.p12)", widget=forms.ClearableFileInput(attrs={"accept": ".pfx,.p12"}), help_text="Arquivo A1 de até 1 MB. Se houver erro ao salvar, selecione o arquivo novamente.")
    senha_a1 = forms.CharField(required=False, strip=False, widget=forms.PasswordInput(render_value=False), label="Senha do A1")
    csc = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False), label="CSC (deixe vazio para manter)")

    class Meta:
        model = ConfiguracaoFiscal
        fields = ['serie_padrao','exigir_classificacao_individual','ativa','ambiente','homologacao_validada','producao_validada','modelo_mercadorias',
            'cnpj','razao_social','nome_fantasia','ie','im','crt','uf','municipio_ibge','municipio',
            'logradouro','numero','complemento','bairro','cep','telefone','email','natureza_operacao','csc_id','qr_code_versao','endpoints','parametros_nfse']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo, tamanho in (('cnpj', 18), ('cep', 9), ('telefone', 22)):
            self.fields[campo].widget.attrs['maxlength'] = tamanho

    def clean_uf(self):
        return self.cleaned_data['uf'].upper()

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


class SolicitacaoForm(EstiloForm, TransporteCampos, ObservacaoCampos):
    rascunho=forms.UUIDField(required=False,widget=forms.HiddenInput())
    valor_frete=forms.DecimalField(required=False,initial=0,min_value=0,max_value=9999999999.99,max_digits=12,decimal_places=2,localize=True,label="Valor do frete (R$)",help_text="Informe somente o frete. O valor das peças vem da origem e o total final aparece na conferência. Use zero quando não houver cobrança.",widget=forms.TextInput(attrs={'inputmode':'decimal','placeholder':'0,00'}))
    difal_aliquota_interna=forms.DecimalField(required=False,min_value=0,max_value=100,max_digits=7,decimal_places=4,localize=True,label="Alíquota interna da UF de destino (%)",help_text="Alíquota do produto no destino, sem incluir o FCP. Confirme com a contabilidade.")
    difal_aliquota_fcp=forms.DecimalField(required=False,min_value=0,max_value=100,max_digits=7,decimal_places=4,localize=True,label="FCP da UF de destino (%)",help_text="Informe explicitamente 0 quando não houver FCP. Vazio significa não confirmado.")
    difal_base_integral_preco_final=forms.BooleanField(required=False,label="Confirmo o preço final com impostos e a base integral, sem redução",help_text="O DIFAL será destacado dentro do preço da nota. Operações com redução ou isenção exigem outro enquadramento.")

    def clean_valor_frete(self):
        from decimal import Decimal
        return self.cleaned_data.get('valor_frete') or Decimal('0')
    destinatario_nome=forms.CharField(required=False,max_length=160,label="Nome / razão social")
    destinatario_documento=CampoNumericoFormatado(required=False,max_length=14,label="CPF/CNPJ",widget=forms.TextInput(attrs={'maxlength':18}))
    destinatario_ind_ie=forms.ChoiceField(required=False,choices=[('', 'Selecione a condição do cliente'),('1','Contribuinte do ICMS'),('2','Isento de inscrição estadual'),('9','Não contribuinte do ICMS')],label="Condição do cliente")
    destinatario_ie=forms.CharField(required=False,max_length=30,label="Inscrição estadual")
    destinatario_logradouro=forms.CharField(required=False,max_length=200,label="Logradouro")
    destinatario_numero=forms.CharField(required=False,max_length=20,label="Número")
    destinatario_complemento=forms.CharField(required=False,max_length=60,label="Complemento")
    consumidor_final=forms.ChoiceField(required=False,initial='1',label="Consumidor final",choices=[('1','Sim — consumo final'),('0','Não — revenda ou industrialização')])
    destinatario_bairro=forms.CharField(required=False,max_length=100,label="Bairro")
    destinatario_municipio=forms.CharField(required=False,max_length=100,label="Município")
    destinatario_municipio_ibge=forms.CharField(required=False,max_length=7,label="Código IBGE do município")
    destinatario_uf=forms.ChoiceField(required=False,choices=[('', 'Selecione a UF')]+[(uf,uf) for uf in sorted('RO AC AM RR PA AP TO MA PI CE RN PB PE AL SE BA MG ES RJ SP PR SC RS MS MT GO DF'.split())],label="UF")
    destinatario_cep=CampoNumericoFormatado(required=False,max_length=8,label="CEP",widget=forms.TextInput(attrs={'maxlength':9}))

    def __init__(self,*args,usuario=None,modelo_padrao='55',**kwargs):
        self.usuario=usuario
        super().__init__(*args,usuario=usuario,**kwargs)
        from clientes.integracao import configurar_seletor
        configurar_seletor(self,usuario,'cliente_cadastro','cliente','Cliente do cadastro',
            {k:'destinatario_'+k for k in ('nome','documento','ie','ind_ie','logradouro','numero','complemento','bairro','municipio','municipio_ibge','uf','cep')})
        self.modelo_padrao=modelo_padrao
        self.fields['modelo'].initial=modelo_padrao
        self.fields['destinatario'].widget=forms.HiddenInput()
        self.fields['destinatario_documento'].widget.attrs['maxlength']=18
        self.fields['destinatario_cep'].widget.attrs['maxlength']=9
        if usuario is not None:
            from vendas.models import Venda
            from comercial.models import Documento
            vendas=Venda.objects.filter(status='concluida').select_related('cliente') if usuario.has_perm('vendas.view_venda') else Venda.objects.none()
            if not usuario.has_perm('vendas.ver_todas_vendas'):vendas=vendas.filter(vendedor=usuario)
            ordens=Documento.objects.filter(tipo='os',status__in=['finalizada','entregue','convertido']).select_related('cliente') if usuario.has_perm('comercial.view_documento') else Documento.objects.none()
            self.fields['venda']=forms.ModelChoiceField(queryset=vendas,required=False,label='Venda concluída',empty_label='Selecione a venda',widget=forms.Select(attrs={'class':'form-select'}))
            self.fields['venda'].label_from_instance=lambda obj:f'{obj.codigo} · {obj.cliente or obj.cliente_nome or "Consumidor"} · R$ {obj.total:.2f}'
            self.fields['ordem_servico']=forms.ModelChoiceField(queryset=ordens,required=False,label='Ordem de serviço concluída',empty_label='Selecione a OS',widget=forms.Select(attrs={'class':'form-select'}))
            self.fields['ordem_servico'].label_from_instance=lambda obj:f'{obj.codigo} · {obj.cliente}'

    def clean_venda(self):
        value=self.cleaned_data.get('venda')
        return value.pk if hasattr(value,'pk') else value

    def clean_ordem_servico(self):
        value=self.cleaned_data.get('ordem_servico')
        return value.pk if hasattr(value,'pk') else value

    aliquota_icms = forms.DecimalField(required=False,min_value=0,max_value=100,max_digits=7,decimal_places=4,label="Alíquota de ICMS desta nota (%)",help_text="Selecione a alíquota correspondente à operação.",
        widget=forms.Select(choices=[('', 'Conforme perfil da peça'),('18','18% — operação interna em SP'),('12','12% — operação interestadual'),('7','7% — operação interestadual'),('4','4% — importados, quando aplicável')]))
    cfop = forms.ChoiceField(required=False,label="CFOP desta nota",choices=[('', 'Conforme perfil e destinatário'),
        ('5102','5.102 — Venda interna em SP'),('6102','6.102 — Venda interestadual a contribuinte'),
        ('6108','6.108 — Venda interestadual a não contribuinte')])
    natureza_operacao = forms.CharField(max_length=60, required=False, label="Natureza da operação", help_text="Vazio usa a natureza do perfil ou da empresa.")

    def clean_cfop(self):
        value = self.cleaned_data['cfop']
        if value:
            from .operacoes import validar_cfop
            try:validar_cfop(value, Operacao.SAIDA)
            except ErroFiscal as erro:raise forms.ValidationError(str(erro)) from None
        return value

    venda = forms.IntegerField(required=False,min_value=1,label="Número interno da venda")
    ordem_servico = forms.IntegerField(required=False,min_value=1,label="Número interno da OS")
    modelo = forms.ChoiceField(choices=[('', 'Conforme configuração')]+list(Modelo.choices),required=False)
    serie = forms.IntegerField(min_value=1,max_value=999,initial=1)
    destinatario = forms.JSONField(required=False,initial=dict,help_text="Endereço fiscal estruturado do destinatário quando necessário. Não altera o cadastro do cliente.")

    def clean(self):
        dados=super().clean()
        if bool(dados.get('venda'))==bool(dados.get('ordem_servico')):
            raise forms.ValidationError('Informe uma venda ou uma OS.')
        if dados.get('valor_frete') and (dados.get('modelo') or self.modelo_padrao)!='55':
            self.add_error('valor_frete','A cobrança de frete está disponível para NF-e (55).')
        dados['difal']=None
        if (dados.get('difal_aliquota_interna') is not None or dados.get('difal_aliquota_fcp') is not None or dados.get('difal_base_integral_preco_final')):
            for campo in ('difal_aliquota_interna','difal_aliquota_fcp'):
                if dados.get(campo) is None:self.add_error(campo,'Confirme este percentual; informe 0 quando não houver FCP.')
            if not dados.get('difal_base_integral_preco_final'):
                self.add_error('difal_base_integral_preco_final','Confirme a base integral no preço final para usar este cálculo.')
            dados['difal']=dict(aliquota_interna=dados.get('difal_aliquota_interna'),aliquota_fcp=dados.get('difal_aliquota_fcp'),base_integral_preco_final=dados.get('difal_base_integral_preco_final'))
        if dados.get('destinatario') is not None and not isinstance(dados['destinatario'],dict):
            raise forms.ValidationError('Dados do destinatário inválidos.')
        cliente=dados.get('cliente_cadastro')
        if not cliente and self.usuario and bool(dados.get('venda'))!=bool(dados.get('ordem_servico')):
            from .preparacao import buscar_origem
            try:cliente=buscar_origem(self.usuario,venda_id=dados.get('venda'),os_id=dados.get('ordem_servico')).cliente
            except (ValueError,Http404):cliente=None
        dest=cliente.dados_fiscais() if cliente else {}
        dest.update(dados.get('destinatario') or {})
        for campo in ('nome','documento','ind_ie','ie','logradouro','numero','complemento','bairro','municipio','municipio_ibge','uf','cep'):
            if dados.get('destinatario_'+campo):dest[campo]=dados['destinatario_'+campo]
        if (dados.get('modelo') or self.modelo_padrao)=='55':
            for campo in ('nome','documento','ind_ie','logradouro','numero','bairro','municipio','municipio_ibge','uf','cep'):
                if not dest.get(campo):self.add_error('destinatario_'+campo,'Preencha este dado para a NF-e.')
            import re
            documento=re.sub(r'[.\s/()-]','',str(dest.get('documento','')))
            if documento and not re.fullmatch(r'(?:[0-9]{11}|[0-9]{14})',documento):self.add_error('destinatario_documento','Informe CPF com 11 ou CNPJ com 14 dígitos.')
            dest['documento']=documento
            cep=re.sub(r'[.\s-]','',str(dest.get('cep','')))
            if cep and not re.fullmatch(r'[0-9]{8}',cep):self.add_error('destinatario_cep','Informe CEP com 8 dígitos.')
            dest['cep']=cep
            if dest.get('municipio_ibge') and not re.fullmatch(r'[0-9]{7}',str(dest['municipio_ibge'])):self.add_error('destinatario_municipio_ibge','Informe o código IBGE com 7 dígitos.')
            if dest.get('ind_ie')=='1' and not dest.get('ie'):self.add_error('destinatario_ie','Informe a inscrição estadual do contribuinte.')
        dados['destinatario']=dest
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
    def __init__(self, *args, crt=None, **kwargs):
        super().__init__(*args, **kwargs)
        novos=('base_pis_cofins','ibscbs_ativo','cst_ibscbs','cclass_trib','aliquota_ibs_uf','aliquota_ibs_municipal','aliquota_cbs')
        if self.is_bound and not any(nome in self.data for nome in novos):
            self.data=self.data.copy()
            for nome in novos:
                valor=getattr(self.instance,nome)
                self.data[nome]=('on' if valor else '') if isinstance(valor,bool) else str(valor)
        self.fields['operacao'].widget = forms.HiddenInput()
        self.fields['operacao'].disabled = True
        individual = 'peca' in self.fields
        if individual:
            self.fields['peca'].required = True
        if individual and self.instance.peca_id:
            peca=self.instance.peca
            if peca.classificacao_fiscal_no_estoque or peca.ncm or peca.origem_fiscal or peca.cest or peca.classificacao_fiscal_conferida:
                self.initial.update(ncm=peca.ncm,origem=peca.origem_fiscal,cest=peca.cest,classificacao_conferida=peca.classificacao_fiscal_conferida)
        self.fields['ncm'].required = individual
        self.fields['origem'].required = individual
        self.fields['ncm'].help_text = 'Código específico da peça, conforme classificação da contabilidade.' if individual else 'Deixe vazio quando o NCM deve ser definido por peça.'
        self.fields['origem'].help_text = 'Confirme a procedência da peça antes de selecionar a origem.'
        self.fields['classificacao_conferida'].help_text = 'Confirme o NCM, a origem e se o CEST se aplica a esta peça.'
        if not individual:
            self.fields['classificacao_conferida'].widget = forms.HiddenInput()
            self.fields['classificacao_conferida'].disabled = True
            self.initial['classificacao_conferida'] = False
        if self.instance.operacao == Operacao.ENTRADA:
            for campo in ('cfop_interestadual_contribuinte','cfop_interestadual_nao_contribuinte'):
                self.fields[campo].widget = forms.HiddenInput()
                self.fields[campo].disabled = True
                self.initial[campo] = ''
        if crt == '3':
            self.fields['csosn'].required = False
            self.fields['csosn'].disabled = True
            self.fields['csosn'].widget = forms.HiddenInput()
            self.initial['csosn'] = ''

    def save(self, commit=True):
        from django.db import transaction
        parametro=super().save(commit=False)
        if commit:
            with transaction.atomic():
                parametro.save()
                self.save_m2m()
                if parametro.peca_id:
                    from estoque.models import Peca
                    peca=Peca.objects.select_for_update().get(pk=parametro.peca_id)
                    peca.classificacao_fiscal_no_estoque=True
                    peca.ncm=parametro.ncm;peca.origem_fiscal=parametro.origem
                    peca.cest=parametro.cest;peca.classificacao_fiscal_conferida=parametro.classificacao_conferida
                    peca.save(update_fields=['classificacao_fiscal_no_estoque','ncm','origem_fiscal','cest','classificacao_fiscal_conferida','atualizado_em'])
        return parametro

    def clean_tributos_adicionais(self):
        dados=self.cleaned_data.get('tributos_adicionais')
        if dados is None:return {}
        if not isinstance(dados,dict):raise forms.ValidationError('Informe um objeto JSON.')
        return dados

    class Meta:
        model=ParametroProduto
        fields=['peca','operacao','natureza_operacao','classificacao_conferida','ncm','cfop','cfop_interestadual_contribuinte','cfop_interestadual_nao_contribuinte','origem','unidade','cest','csosn','cst_icms','aliquota_icms',
                'cst_pis','aliquota_pis','cst_cofins','aliquota_cofins','base_pis_cofins','ibscbs_ativo','cst_ibscbs','cclass_trib','aliquota_ibs_uf','aliquota_ibs_municipal','aliquota_cbs','tributos_adicionais']


class ProdutoPadraoForm(ProdutoForm):
    class Meta(ProdutoForm.Meta):
        fields = [campo for campo in ProdutoForm.Meta.fields if campo != 'peca']


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
class CartaCorrecaoForm(EstiloForm, forms.Form):
    chave=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    texto=forms.CharField(label='Texto consolidado da correção',min_length=15,max_length=1000,widget=forms.Textarea,
        help_text='Inclua todas as correções válidas, inclusive as de cartas anteriores. A CC-e não altera valores, quantidades, bases, alíquotas, identidade de remetente/destinatário ou datas de emissão/saída.')
    confirmacao=forms.BooleanField(label='Confirmo que esta correção respeita os limites da CC-e.')
