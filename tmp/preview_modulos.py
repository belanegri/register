import os,sys,json
from pathlib import Path
from datetime import date,timedelta
from decimal import Decimal
root=Path.cwd();sys.path.insert(0,str(root));os.environ['DJANGO_SETTINGS_MODULE']='pontocar.test_settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
settings.ALLOWED_HOSTS=['testserver']
import django
django.setup()
from django.apps import apps
settings.MIGRATION_MODULES={a.label:None for a in apps.get_app_configs()}
from django.core.management import call_command
call_command('migrate',verbosity=0,interactive=False,run_syncdb=True)
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.db import models
from estoque.models import Peca,Categoria
from clientes.models import Cliente
from caixa.models import SessaoCaixa
from vendas.models import Venda,ItemVenda,FormaPagamento
from comercial.models import Documento,Servico,ContaReceber
from contas.models import ContaPagar
user=get_user_model().objects.create_superuser('operador_preview',password='somente-preview-local')
cliente=Cliente.objects.create(nome='Oficina Exemplo',documento='Cliente demonstrativo',telefone='(11) 99999-0000')
cat=Categoria.objects.create(nome='Elétrica e iluminação')
peca=Peca.objects.create(codigo='REG000001',nome='Farol dianteiro esquerdo',categoria=cat,marca='Fiat',aplicacao='Palio 2012',preco_venda=250,quantidade=3)
Peca.objects.create(codigo='REG000002',nome='Alternador 90 amperes',categoria=cat,marca='Volkswagen',aplicacao='Gol G5',preco_venda=380,quantidade=2,status='reservada')
servico=Servico.objects.create(nome='Instalação de peça',valor_padrao=80,categoria='Mão de obra')
caixa=SessaoCaixa.objects.create(operador=user,saldo_inicial=100)
venda=Venda.objects.create(vendedor=user,caixa=caixa,cliente=cliente,cliente_nome=cliente.nome,subtotal=250,total=250)
ItemVenda.objects.create(venda=venda,peca=peca,descricao=peca.nome,quantidade=1,preco_unitario=250,custo_unitario=100,total=250)
FormaPagamento.objects.create(nome='Dinheiro',dinheiro=True)
FormaPagamento.objects.create(nome='PIX')
docs=[]
for tipo,status in [('orcamento','enviado'),('os','andamento')]:
    d=Documento(tipo=tipo,status=status,cliente=cliente,criado_por=user)
    for f in d._meta.concrete_fields:
        if not f.primary_key and not f.null and getattr(d,f.attname) is None:
            if isinstance(f,models.DecimalField):setattr(d,f.attname,Decimal('0'))
            elif isinstance(f,models.IntegerField):setattr(d,f.attname,0)
            elif isinstance(f,models.DateField):setattr(d,f.attname,date.today())
    d.save();docs.append(d)
receber=ContaReceber.objects.create(cliente=cliente,descricao='Peças e serviços da oficina',valor_original=450,vencimento=date.today()-timedelta(days=3),criado_por=user)
pagar=ContaPagar.objects.create(descricao='Compra de peças',fornecedor='Distribuidora Exemplo',valor=300,vencimento=date.today()-timedelta(days=2),criado_por=user)
client=Client();client.force_login(user)
routes=[('painel','dashboard:index',[]),('estoque','estoque:lista',[]),('peca','estoque:detalhe',[peca.pk]),('editar-peca','estoque:editar',[peca.pk]),('clientes','clientes:lista',[]),('cliente','clientes:detalhe',[cliente.pk]),('novo-cliente','clientes:novo',[]),('orcamentos','comercial:documentos',['orcamento']),('ordens','comercial:documentos',['os']),('orcamento','comercial:detalhe',[docs[0].pk]),('ordem','comercial:detalhe',[docs[1].pk]),('novo-orcamento','comercial:novo',['orcamento']),('nova-ordem','comercial:novo',['os']),('servicos','comercial:servicos',[]),('novo-servico','comercial:servico_novo',[]),('vendas','vendas:lista',[]),('venda','vendas:detalhe',[venda.pk]),('relatorios','vendas:relatorios',[]),('caixa','caixa:painel',[]),('movimentos','caixa:detalhe',[caixa.pk]),('receber','comercial:contas',[]),('cobranca','comercial:conta',[receber.pk]),('nova-cobranca','comercial:conta_nova',[]),('pagar','contas:lista',[]),('conta-pagar','contas:detalhe',[pagar.pk]),('nova-despesa','contas:nova',[]),('fiscal','fiscal:lista',[]),('empresa','core:configuracao_empresa',[]),('administracao','admin:index',[]),('veiculos','admin:veiculos_veiculo_changelist',[]),('cadastro-veiculo','admin:veiculos_veiculo_add',[]),('pdv','vendas:pdv',[])]
out=root/'tmp/modulos-preview';out.mkdir(exist_ok=True)
(out/'jsi18n.js').write_bytes(client.get('/admin/jsi18n/').content)
results=[]
for name,route,args in routes:
    response=client.get(reverse(route,args=args))
    assert response.status_code==200,(name,response.status_code)
    html=response.content.decode().replace(settings.STATIC_URL,(root/'static').as_uri()+'/')
    html=html.replace((root/'static/admin').as_uri()+'/',(root/'.venv/Lib/site-packages/django/contrib/admin/static/admin').as_uri()+'/').replace('src="/admin/jsi18n/"','src="'+(out/'jsi18n.js').as_uri()+'"')
    (out/(name+'.html')).write_text(html,encoding='utf-8')
    results.append({'nome':name,'rota':route,'status':response.status_code})
(out/'paginas.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'paginas':len(results),'status':'ok','banco':'sqlite temporario em memoria'},ensure_ascii=False))
