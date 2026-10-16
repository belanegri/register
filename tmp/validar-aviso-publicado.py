import runpy, subprocess, hashlib, json
from pathlib import Path
root=Path.cwd()
h=runpy.run_path(str(root/'.local/fiscal-publicacao.py'))
files=['estoque/etiqueta_pdf.py','estoque/test_etiqueta_pdf.py','static/js/etiqueta.js','templates/impressao/etiqueta.html']
hashes={f:hashlib.sha256((root/f).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for f in files}
code='''import hashlib,json
from pathlib import Path
from django.core.management import call_command
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from estoque.models import Peca
from estoque.views import etiqueta
hashes=HASHES
assert all(hashlib.sha256(Path(f).read_bytes().replace(bytes([13,10]),bytes([10]))).hexdigest()==v for f,v in hashes.items())
call_command('test','estoque.test_etiqueta_pdf.EtiquetaPDFTests',verbosity=1)
p=Peca.objects.first()
u=get_user_model().objects.filter(is_active=True,is_superuser=True).first()
assert p and u
for modelo in ('padrao','online'):
    r=RequestFactory().get('/etiqueta/',{'modelo':modelo});r.user=u
    response=etiqueta(r,p.pk)
    assert response.status_code==200
    assert (b'class="etiqueta-online"' in response.content)==(modelo=='online')
    assert (b'class="etiqueta-barras"' in response.content)==(modelo=='padrao')
print('AVISO_QA='+json.dumps({'arquivos':len(hashes),'testes':3,'paginas':'ok'}))
'''.replace('HASHES',repr(hashes))
def debug_cli(args):
    r=subprocess.run([h['CLI']]+args,cwd=root,capture_output=True,text=True,encoding='utf-8',timeout=120)
    if r.returncode:
        print(r.stdout[-4000:],r.stderr[-4000:]);raise RuntimeError('Verificação remota falhou')
    return r.stdout
for nome,p,e,s in h['TARGETS']:
    out=debug_cli(['ssh']+h['flags'](p,e,s)+['-i',str(root/'.local/register_railway_ed25519'),'--','python','manage.py','shell','-c',code])
    print(nome,next(l for l in out.splitlines() if l.startswith('AVISO_QA=')),flush=True)
