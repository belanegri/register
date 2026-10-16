import os, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE']='pontocar.test_settings'
from django.conf import settings
base = Path(__file__).resolve().parents[1]
saida = base / 'tmp/financeiro-preview'
saida.mkdir(exist_ok=True)
settings.DATABASES = {'default':{'ENGINE':'django.db.backends.sqlite3','NAME':str(saida/'preview-sem-migrations.sqlite3')}}
settings.MIGRATION_MODULES = {nome:None for nome in settings.INSTALLED_APPS if not nome.startswith('django.')}
settings.ALLOWED_HOSTS = ['testserver']
import django
django.setup()
from django.core.management import call_command
call_command('migrate',verbosity=0,interactive=False,run_syncdb=True)
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db import transaction
from clientes.models import Cliente
from contas.models import ContaPagar
from comercial.forms import ContaForm
from comercial.services import criar_conta_receber
from vendas.models import FormaPagamento
from datetime import date
import uuid
with transaction.atomic():
    user = get_user_model().objects.create_superuser('preview-financeiro-'+uuid.uuid4().hex[:8])
    cliente = Cliente.objects.create(nome='Oficina Exemplo',documento='Cliente demonstrativo')
    pix,_ = FormaPagamento.objects.get_or_create(nome='PIX',defaults={'ativa':True})
    form = ContaForm(dict(cliente=cliente.pk,descricao='Peças e serviços · OS demonstrativa',valor_original='450',
        vencimento='2027-01-31',chave=str(uuid.uuid4()),quantidade_lancamentos='3',frequencia='mensal',forma_prevista=pix.pk))
    assert form.is_valid(),form.errors
    criar_conta_receber(user,form.cleaned_data)
    ContaPagar.objects.create(descricao='Compra de peças',fornecedor='Distribuidora Exemplo',valor=300,
        vencimento=date(2027,1,15),criado_por=user,forma_prevista=pix)
    client=Client();client.force_login(user)
    for nome,url in [('receber',reverse('comercial:contas')),('pagar',reverse('contas:lista')),('nova-receber',reverse('comercial:conta_nova')),('nova-pagar',reverse('contas:nova'))]:
        response=client.get(url)
        assert response.status_code==200,(url,response.status_code)
        html=response.content.decode().replace(settings.STATIC_URL,(base/'static').as_uri()+'/')
        (saida/(nome+'.html')).write_text(html,encoding='utf-8')
    transaction.set_rollback(True)
print('Prévias com dados sintéticos geradas em',saida)
