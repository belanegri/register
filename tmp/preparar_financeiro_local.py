import os,sys,subprocess
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','pontocar.settings')
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.core.management import call_command
config=settings.DATABASES['default']
assert config['HOST'] in ['127.0.0.1','localhost','::1'] and str(config['PORT'])=='5433','Somente desenvolvimento local.'
queries=[
 'SELECT id,cliente_id,descricao,origem,venda_id,os_id,valor_original,vencimento,cancelada,observacoes FROM comercial_contareceber ORDER BY id',
 'SELECT id,descricao,fornecedor,valor,vencimento,status,movimento_id FROM contas_contapagar ORDER BY id',
 'SELECT id,valor FROM caixa_movimentocaixa ORDER BY id',
 'SELECT id,status,total FROM vendas_venda ORDER BY id',
 'SELECT id,quantidade,status FROM estoque_peca ORDER BY id',
]
def snapshot():
    with connection.cursor() as c:
        resultado=[]
        for query in queries:
            c.execute(query);resultado.append(c.fetchall())
        return resultado
antes=snapshot()
destino=Path('.local/backups');destino.mkdir(exist_ok=True)
arquivo=destino/('antes-receber-parcelamento-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.dump')
env=os.environ.copy();env['PGPASSWORD']=config['PASSWORD']
r=subprocess.run([str(Path('.local/pgsql/bin/pg_dump.exe').resolve()),'-h',config['HOST'],'-p',str(config['PORT']),
    '-U',config['USER'],'-d',config['NAME'],'-Fc','-f',str(arquivo.resolve())],env=env,capture_output=True)
assert r.returncode==0,'Backup local falhou; nenhuma migration aplicada.'
call_command('migrate','comercial',interactive=False,verbosity=1)
call_command('migrate','contas',interactive=False,verbosity=1)
assert antes==snapshot(),'Verifique os dados antes de continuar.'
print('Banco local atualizado; valores e vínculos de contas, caixa, vendas e estoque preservados.')
print('Backup:',arquivo)
