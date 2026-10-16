import os,sys,uuid
from pathlib import Path
from types import SimpleNamespace as Obj
from decimal import Decimal
from unittest.mock import patch
root=Path.cwd();sys.path.insert(0,str(root))
os.environ['DJANGO_SETTINGS_MODULE']='pontocar.test_settings'
import django
django.setup()
from django.template.loader import render_to_string
from vendas.forms import CheckoutForm,PagamentosFormSet
class Perms:
    def __getattr__(self,name): return self
    def __bool__(self): return True
pecas=[Obj(pk=i,nome=n,codigo=f'REG00000{i}',marca=m,aplicacao=a,posicao='',quantidade=q,localizacao=l,preco_venda=Decimal(v),fotos=Obj(all=[])) for i,n,m,a,q,l,v in [(1,'Farol dianteiro esquerdo','Fiat','Palio 2012',3,'A-02','250'),(2,'Alternador 90 amperes','Volkswagen','Gol G5',2,'B-04','380'),(3,'Retrovisor externo direito','Chevrolet','Onix 2018',5,'C-01','180'),(4,'Para-choque dianteiro','Toyota','Corolla 2015',1,'D-03','620')]]
saida=root/'tmp/pdv-preview';saida.mkdir(exist_ok=True)
for nome,vazio,fechado in [('cheio',False,False),('vazio',True,True)]:
    with patch('core.documentos.empresa_atual',return_value={}): form=CheckoutForm(initial={'chave':uuid.uuid4()})
    form.fields['cliente'].choices=[('','Consumidor não identificado'),('1','Oficina Exemplo')]
    pagamentos=PagamentosFormSet(prefix='pag')
    for f in pagamentos:
        f.fields['forma'].choices=[('','Selecione'),('1','Dinheiro'),('2','PIX'),('3','Cartão')]
    linhas=[] if vazio else [dict(id=str(p.pk),peca=p,quantidade=1,preco=p.preco_venda,total=p.preco_venda) for p in pecas[:2]]
    ctx=dict(user=Obj(is_authenticated=True,is_staff=True,username='Operador'),perms=Perms(),request=Obj(resolver_match=Obj(app_name='vendas',url_name='pdv')),csrf_token='preview',empresa_nome='PontoCar',linhas=linhas,pecas=pecas,servicos=[Obj(pk=1,nome='Instalação de peça',valor_padrao=Decimal('80'))],subtotal=sum(l['total'] for l in linhas),caixa=None if fechado else Obj(codigo='CX000018'),form=form,pagamentos=pagamentos,q='')
    html=render_to_string('vendas/pdv.html',ctx).replace('/static/',(root/'static').as_uri()+'/')
    html=html.replace('<option value="1">Dinheiro','<option value="1" data-dinheiro="1">Dinheiro')
    (saida/(nome+'.html')).write_text(html,encoding='utf-8')
print('Prévias geradas com dados demonstrativos, sem acesso ao banco.')
