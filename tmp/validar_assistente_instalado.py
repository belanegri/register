import json,urllib.request
from pathlib import Path
from html.parser import HTMLParser
class Etiqueta(HTMLParser):
    def handle_starttag(self, tag, attrs):
        dados=dict(attrs)
        if dados.get('id')=='imprimir':self.pdf=dados['data-etiqueta']
p=Etiqueta();p.feed(Path('tmp/etiqueta-multicomputador.html').read_text(encoding='utf-8'))
corpo=json.dumps({'pdf':p.pdf,'pedido':'validacao-instalador-20261006'}).encode()
req=urllib.request.Request('http://127.0.0.1:17857/validar',data=corpo,
    headers={'Origin':'https://register-production-351c.up.railway.app','Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=10) as resposta:
    resultado=json.load(resposta)
    assert resultado['status']=='validada' and resultado['altura_pontos']==240 and resultado['tinta_pontos']>20
    print('Assistente instalado:',resultado)
