import hashlib
import json
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
h = runpy.run_path(str(root / '.local/fiscal-publicacao.py'))
files = [
    'static/css/modulos.css', 'static/css/admin-register.css', 'static/js/modulos.js',
    'templates/base.html', 'templates/admin/base_site.html', 'templates/dashboard/index.html',
    'templates/caixa/painel.html', 'templates/clientes/lista.html', 'templates/comercial/lista.html',
    'templates/comercial/servicos.html', 'templates/comercial/contas.html', 'templates/contas/lista.html',
    'templates/estoque/lista.html', 'templates/fiscal/lista.html', 'templates/fiscal/menu.html',
    'templates/vendas/relatorios.html', 'templates/vendas/tabela.html',
]
hashes = {f: hashlib.sha256((root / f).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for f in files}
code = '''import hashlib,json
from pathlib import Path
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse,resolve
from django.contrib.staticfiles.storage import staticfiles_storage
hashes=HASHES
assert all(hashlib.sha256(Path(f).read_bytes().replace(bytes([13,10]),bytes([10]))).hexdigest()==v for f,v in hashes.items()), 'Arquivos divergentes'
call_command('check')
for asset in ['css/modulos.css','css/admin-register.css','js/modulos.js']:
    assert staticfiles_storage.exists(staticfiles_storage.stored_name(asset)), asset
user=get_user_model().objects.filter(is_active=True,is_superuser=True,is_staff=True).first()
assert user is not None
routes=[('dashboard:index',[]),('estoque:lista',[]),('clientes:lista',[]),('clientes:novo',[]),('comercial:documentos',['orcamento']),('comercial:documentos',['os']),('comercial:servicos',[]),('comercial:servico_novo',[]),('comercial:novo',['orcamento']),('comercial:novo',['os']),('vendas:lista',[]),('vendas:relatorios',[]),('vendas:pdv',[]),('caixa:painel',[]),('comercial:contas',[]),('comercial:conta_nova',[]),('contas:lista',[]),('contas:nova',[]),('fiscal:lista',[]),('fiscal:nfe',[]),('fiscal:nfce',[]),('fiscal:nfse',[]),('fiscal:eventos',[]),('admin:index',[]),('admin:veiculos_veiculo_changelist',[]),('admin:estoque_categoria_changelist',[]),('admin:estoque_localizacao_changelist',[])]
pages=[]
for route,args in routes:
    url=reverse(route,args=args)
    req=RequestFactory().get(url)
    req.user=user
    req.session={}
    req.resolver_match=resolve(url)
    response=req.resolver_match.func(req,**req.resolver_match.kwargs)
    if hasattr(response,'render'): response.render()
    assert response.status_code==200,(route,response.status_code)
    asset='css/admin-register.css' if route.startswith('admin:') else 'css/modulos.css'
    assert staticfiles_storage.url(asset).encode() in response.content, route
    if route=='contas:lista':
        title=response.content.split(b'<title>',1)[1].split(b'</title>',1)[0]
        assert b'<' not in title, 'Titulo invalido'
    pages.append(route+(':'+str(args[0]) if args else ''))
print('MODULOS_QA='+json.dumps({'paginas':len(pages),'arquivos':len(hashes),'estaticos':'disponiveis','layout':'atualizado','dados_modificados':False}))
'''.replace('HASHES', repr(hashes))
for nome, p, e, s in h['TARGETS']:
    if len(sys.argv) > 1 and not nome.endswith(sys.argv[1]):
        continue
    out = h['cli'](['ssh'] + h['flags'](p, e, s) + ['-i', str(root / '.local/register_railway_ed25519'), '--', 'python', 'manage.py', 'shell', '-c', code])
    result = next(l for l in out.splitlines() if l.startswith('MODULOS_QA='))
    print(nome, result, flush=True)
