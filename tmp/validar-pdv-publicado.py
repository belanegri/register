import hashlib
import json
import runpy
from pathlib import Path

root = Path(__file__).resolve().parents[1]
h = runpy.run_path(str(root / '.local/fiscal-publicacao.py'))
files = ['templates/base.html', 'templates/vendas/pdv.html', 'static/css/pdv.css', 'static/js/pdv.js']
hashes = {f: hashlib.sha256((root / f).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for f in files}
code = '''import hashlib,json
from pathlib import Path
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import reverse,resolve
from django.contrib.staticfiles.storage import staticfiles_storage
hashes=HASHES
assert all(hashlib.sha256(Path(f).read_bytes().replace(bytes([13,10]),bytes([10]))).hexdigest()==v for f,v in hashes.items())
call_command('check')
user=get_user_model().objects.filter(is_active=True,is_superuser=True).first()
assert user is not None
url=reverse('vendas:pdv')
req=RequestFactory().get(url)
req.user=user
SessionMiddleware(lambda r: None).process_request(req)
req.resolver_match=resolve(url)
response=req.resolver_match.func(req)
assert response.status_code==200
for marker in ('pdv-columns','pdv-pagamento','pdv-vencimento','Total da venda','Escolha os itens'):
    assert marker.encode() in response.content, marker
css=staticfiles_storage.url('css/pdv.css')
assert css.encode() in response.content
assert staticfiles_storage.exists(staticfiles_storage.stored_name('css/pdv.css'))
assert staticfiles_storage.url('js/pdv.js').encode() in response.content
print('PDV_QA='+json.dumps({'pagina':response.status_code,'arquivos':len(hashes),'css':'disponivel','layout':'atualizado','dados_modificados':False}))
'''.replace('HASHES', repr(hashes))
for nome, p, e, s in h['TARGETS']:
    out = h['cli'](['ssh'] + h['flags'](p, e, s) + ['-i', str(root / '.local/register_railway_ed25519'), '--', 'python', 'manage.py', 'shell', '-c', code])
    print(nome, next(l for l in out.splitlines() if l.startswith('PDV_QA=')), flush=True)
