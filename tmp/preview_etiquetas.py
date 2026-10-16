import os,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE']='pontocar.test_settings'
import django;django.setup()
from django.template.loader import render_to_string
from estoque.etiqueta_pdf import gerar_etiqueta_pdf
from estoque.codigo_barras import gerar_svg
from base64 import b64encode,urlsafe_b64encode
base=Path(__file__).resolve().parents[1]
peca=SimpleNamespace(pk=1,codigo='REG000001',nome='Peça de teste',marca='Fiat',aplicacao='Uno',
    ano_inicial=1992,ano_final=1998,posicao='Esquerdo')
html=render_to_string('impressao/etiqueta.html',{'peca':peca,'etiqueta_direta':urlsafe_b64encode(gerar_etiqueta_pdf(peca)).decode().rstrip('='),
    'codigo_barras_etiqueta':b64encode(gerar_svg(peca.codigo).encode()).decode()})
(base/'tmp/etiqueta-multicomputador.html').write_text(html.replace('/static/',(base/'static').as_uri()+'/'),encoding='utf-8')
