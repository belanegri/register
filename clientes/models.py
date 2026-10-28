from django.db import models
from core.models import TimestampedModel


class Cliente(TimestampedModel):
    nome = models.CharField(max_length=160, db_index=True)
    nome_fantasia = models.CharField('nome fantasia / apelido', max_length=160, blank=True, default='', db_default='')
    eh_cliente = models.BooleanField('Cliente', default=True, db_default=True)
    eh_fornecedor = models.BooleanField('Fornecedor', default=False, db_default=False)
    eh_transportadora = models.BooleanField('Transportadora', default=False, db_default=False)
    contato = models.CharField('pessoa de contato', max_length=120, blank=True, default='', db_default='')
    whatsapp = models.CharField('WhatsApp', max_length=30, blank=True, default='', db_default='')
    email_financeiro = models.EmailField('e-mail financeiro', blank=True, default='', db_default='')
    inscricao_estadual = models.CharField('inscrição estadual', max_length=14, blank=True, default='', db_default='')
    indicador_ie = models.CharField('situação perante o ICMS', max_length=1, default='9', db_default='9', choices=[('1','Contribuinte do ICMS'),('2','Isento de inscrição'),('9','Não contribuinte')])
    cep = models.CharField('CEP', max_length=8, blank=True, default='', db_default='')
    logradouro = models.CharField(max_length=200, blank=True, default='', db_default='')
    numero = models.CharField('número', max_length=20, blank=True, default='', db_default='')
    complemento = models.CharField(max_length=60, blank=True, default='', db_default='')
    bairro = models.CharField(max_length=100, blank=True, default='', db_default='')
    municipio = models.CharField('município', max_length=100, blank=True, default='', db_default='')
    municipio_ibge = models.CharField('código IBGE do município', max_length=7, blank=True, default='', db_default='')
    uf = models.CharField('UF', max_length=2, blank=True, default='', db_default='', choices=[(u,u) for u in sorted('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())])
    rntrc = models.CharField('ANTT / RNTRC', max_length=20, blank=True, default='', db_default='')
    documento = models.CharField("CPF/CNPJ", max_length=20, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    endereco = models.TextField("endereço", blank=True)
    observacoes = models.TextField("observações", blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome", "pk"]
        verbose_name = "pessoa ou empresa"
        verbose_name_plural = "pessoas e empresas"

    def __str__(self):
        return self.nome


    @property
    def papeis(self):
        return ' · '.join(rotulo for campo,rotulo in [('eh_cliente','Cliente'),('eh_fornecedor','Fornecedor'),('eh_transportadora','Transportadora')] if getattr(self,campo))

    @property
    def endereco_completo(self):
        if not self.logradouro:
            return self.endereco
        return ', '.join(str(v) for v in (self.logradouro,self.numero,self.complemento,self.bairro,self.municipio,self.uf,self.cep) if v)

    @property
    def pendencias_fiscais(self):
        campos=[('documento','CPF/CNPJ'),('logradouro','logradouro'),('numero','número'),('bairro','bairro'),('municipio','município'),('municipio_ibge','código IBGE'),('uf','UF'),('cep','CEP')]
        faltam=[rotulo for campo,rotulo in campos if not getattr(self,campo)]
        if self.indicador_ie=='1' and not self.inscricao_estadual:faltam.append('inscrição estadual')
        return faltam

    def dados_fiscais(self):
        import re
        return dict(cadastro_id=self.pk,nome=self.nome,documento=re.sub(r'[^0-9]','',self.documento),
            ie=self.inscricao_estadual,ind_ie=self.indicador_ie,
            **{k:getattr(self,k) for k in ('logradouro','numero','complemento','bairro','municipio','municipio_ibge','uf','cep')})

    def dados_transporte(self):
        import re
        endereco=', '.join(v for v in (self.logradouro,self.numero,self.complemento,self.bairro) if v) or self.endereco
        return dict(cadastro_id=self.pk,nome=self.nome,documento=re.sub(r'[^0-9]','',self.documento),ie=self.inscricao_estadual,
            endereco=endereco[:60],municipio=self.municipio,uf=self.uf,rntc=self.rntrc)
