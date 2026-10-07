"""Ponte local entre as duas lojas REGISTER e a impressora de etiquetas."""
import json
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from assistente_etiqueta_windows import imprimir, ler_etiqueta, preparar_impressao, listar_impressoras, impressora_configurada, pasta_configuracao

ORIGENS = {
    'https://register-production-351c.up.railway.app',
    'https://register-loja-2-production.up.railway.app',
}
TRAVA = threading.Lock()
RESULTADOS = {}
REGISTRO = pasta_configuracao() / 'ultimo-trabalho.json'


class Etiquetas(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def responder(self, status, resultado):
        corpo = json.dumps(resultado, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        origem = self.headers.get('Origin')
        if origem in ORIGENS:
            self.send_header('Access-Control-Allow-Origin', origem)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(corpo)

    def permitido(self):
        return (self.headers.get('Host') == '127.0.0.1:17857'
                and self.headers.get('Origin') in ORIGENS)

    def do_OPTIONS(self):
        self.responder(200 if self.permitido() else 403, {})

    def do_GET(self):
        if self.path == '/status' and self.headers.get('Host') == '127.0.0.1:17857':
            try:
                self.responder(200, {'assistente': 'REGISTER', 'versao': 'raw30-multicomputador-2',
                    'impressoras': listar_impressoras(), 'impressora': impressora_configurada()})
            except Exception:
                self.responder(503, {'erro': 'Não foi possível consultar as impressoras do Windows.'})
        else:
            self.responder(404, {'erro': 'Endereco invalido.'})

    def do_POST(self):
        if not self.permitido():
            self.responder(403, {'erro': 'Origem nao autorizada.'})
            return
        if self.path not in ('/imprimir', '/validar'):
            self.responder(404, {'erro': 'Endereco invalido.'})
            return
        try:
            tamanho = int(self.headers.get('Content-Length', '0'))
            if not 0 < tamanho <= 17000 or self.headers.get('Content-Type') != 'application/json':
                raise ValueError('Pedido de etiqueta invalido.')
            self.connection.settimeout(5)
            pedido = json.loads(self.rfile.read(tamanho))
            if set(pedido) not in ({'pdf', 'pedido'}, {'pdf', 'pedido', 'impressora'}) or not isinstance(pedido['pdf'], str):
                raise ValueError('Pedido de etiqueta invalido.')
            identificador = pedido['pedido']
            if not isinstance(identificador, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,64}', identificador):
                raise ValueError('Identificador de pedido invalido.')
            uri = 'register-etiqueta://imprimir?pdf=' + pedido['pdf']
            pdf = ler_etiqueta(uri)
            nome = pedido.get('impressora')
            if nome is not None and (not isinstance(nome, str) or nome not in listar_impressoras()):
                raise ValueError('Impressora não instalada neste computador.')
            if self.path == '/validar':
                _, tinta = preparar_impressao(pdf)
                self.responder(200, {'status': 'validada', 'altura_pontos': 240, 'tinta_pontos': tinta})
                return
            with TRAVA:
                if identificador in RESULTADOS:
                    resultado = RESULTADOS[identificador]
                    if resultado.get('destino') != nome or resultado.get('conteudo') != pedido['pdf']:
                        self.responder(409, {'erro': 'Pedido já utilizado para outra etiqueta ou impressora.'})
                        return
                else:
                    registro = {'hora': datetime.now(timezone.utc).isoformat(),
                                'pedido': identificador, 'origem': self.headers['Origin']}
                    try:
                        resultado = dict(imprimir(uri, nome) if nome is not None else imprimir(uri), status='enviada')
                    except Exception as erro:
                        resultado = {'status': 'erro', 'mensagem': str(erro)}
                    registro.update(resultado)
                    resultado.update(destino=nome, conteudo=pedido['pdf'])
                    REGISTRO.write_text(
                        json.dumps(registro), encoding='utf-8')
                    if len(RESULTADOS) >= 1000:
                        RESULTADOS.pop(next(iter(RESULTADOS)))
                    RESULTADOS[identificador] = resultado
            self.responder(200 if resultado['status'] == 'enviada' else 500,
                {k:v for k,v in resultado.items() if k not in ('destino','conteudo')})
        except (ValueError, TypeError, KeyError, TimeoutError) as erro:
            self.responder(400, {'erro': str(erro)})
        except Exception:
            self.responder(500, {'erro': 'Nao foi possivel processar a etiqueta.'})


if __name__ == '__main__':
    servidor = ThreadingHTTPServer(('127.0.0.1', 17857), Etiquetas)
    servidor.daemon_threads = True
    servidor.serve_forever()
