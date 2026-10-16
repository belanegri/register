import hashlib
import runpy
from pathlib import Path

root = Path(__file__).resolve().parents[1]
h = runpy.run_path(str(root / '.local/fiscal-publicacao.py'))
files = ['static/css/modulos.css', 'templates/base.html', 'templates/components/peca_table.html', 'templates/estoque/editar.html']
hashes = {f: hashlib.sha256((root / f).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for f in files}
code = '''import hashlib,json
from pathlib import Path
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse,resolve
from django.contrib.staticfiles.storage import staticfiles_storage
from estoque.models import Peca
hashes=HASHES
assert all(hashlib.sha256(Path(f).read_bytes().replace(bytes([13,10]),bytes([10]))).hexdigest()==v for f,v in hashes.items())
call_command('check')
assert staticfiles_storage.exists(staticfiles_storage.stored_name('css/modulos.css'))
user=get_user_model().objects.filter(is_active=True,is_superuser=True).first()
assert user is not None
routes=[('estoque:lista',[]),('dashboard:index',[]),('vendas:pdv',[]),('contas:lista',[]),('comercial:contas',[])]
peca=Peca.objects.first()
if peca: routes.extend([('estoque:detalhe',[peca.pk]),('estoque:editar',[peca.pk])])
for route,args in routes:
    url=reverse(route,args=args);req=RequestFactory().get(url);req.user=user;req.session={};req.resolver_match=resolve(url)
    response=req.resolver_match.func(req,**req.resolver_match.kwargs)
    assert response.status_code==200, route
    assert b'mobile2' in response.content, route
    if route=='estoque:lista' and peca:
        assert b'pecas-table' in response.content
        assert b'peca-identidade' in response.content
        assert b'peca-acoes' in response.content
print('MOBILE_QA='+json.dumps({'paginas':len(routes),'arquivos':len(hashes),'estoque':'cartoes responsivos publicados','dados_modificados':False}))
'''.replace('HASHES', repr(hashes))
for nome, p, e, s in h['TARGETS']:
    out = h['cli'](['ssh'] + h['flags'](p, e, s) + ['-i', str(root / '.local/register_railway_ed25519'), '--', 'python', 'manage.py', 'shell', '-c', code])
    print(nome, next(l for l in out.splitlines() if l.startswith('MOBILE_QA=')), flush=True)
