import runpy, hashlib, subprocess, json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
h=runpy.run_path(str(root/'.local/fiscal-publicacao.py'))
files=subprocess.check_output(['git','diff-tree','--no-commit-id','--name-only','-r','HEAD'],text=True).splitlines()
hashes={f:hashlib.sha256((root/f).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for f in files}
code='''import json, hashlib
from pathlib import Path
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse, resolve
from estoque.models import Peca
from estoque.forms import PecaAdminForm, PecaEdicaoForm
call_command('check')
assert not MigrationExecutor(connection).migration_plan([('estoque','0006_peca_compativel_peca_postada_online')])
hashes=HASHES
assert all(hashlib.sha256(Path(f).read_bytes().replace(bytes([13,10]),bytes([10]))).hexdigest()==v for f,v in hashes.items())
for form in (PecaAdminForm(),PecaEdicaoForm()):
    assert 'compativel' in form.fields and 'postada_online' in form.fields
user=get_user_model().objects.filter(is_active=True,is_superuser=True).first()
assert user is not None
peca=Peca.objects.first()
checked=[]
if peca:
    for route, params in [('lista',{}),('editar',{}),('detalhe',{}),('etiqueta',{'modelo':'padrao'}),('etiqueta',{'modelo':'online'})]:
        url=reverse('estoque:'+route,args=[] if route=='lista' else [peca.pk])
        req=RequestFactory().get(url,params);req.user=user;req.session={};req.resolver_match=resolve(url)
        response=req.resolver_match.func(req,**req.resolver_match.kwargs)
        assert response.status_code==200
        if route=='etiqueta':
            assert b'data-etiqueta=' in response.content
            assert (b'class="etiqueta-online"' in response.content)==(params['modelo']=='online')
        checked.append(route+(':'+params['modelo'] if params else ''))
print('PECAS_QA='+json.dumps({'migracao':'aplicada','arquivos':len(hashes),'campos':'disponiveis','paginas':checked,'dados_modificados':False}))
'''.replace('HASHES',repr(hashes))
for nome,p,e,s in h['TARGETS']:
    output=h['cli'](['ssh']+h['flags'](p,e,s)+['-i',str(root/'.local/register_railway_ed25519'),'--','python','manage.py','shell','-c',code])
    result=next(l.split('=',1)[1] for l in output.splitlines() if l.startswith('PECAS_QA='))
    print(nome,result,flush=True)
