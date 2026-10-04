import base64
from http.client import HTTPConnection
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

import servidor_etiqueta_windows as ponte


class PonteTests(unittest.TestCase):
    def setUp(self):
        self.pasta = TemporaryDirectory()
        self.registro = patch.object(ponte, 'REGISTRO', Path(self.pasta.name) / 'registro.json')
        self.registro.start()
        ponte.RESULTADOS.clear()
        self.server = ponte.ThreadingHTTPServer(('127.0.0.1', 0), ponte.Etiquetas)
        Thread(target=self.server.serve_forever, daemon=True).start()
        pdf = BytesIO()
        canvas = Canvas(pdf, pagesize=(57 * mm, 30 * mm))
        canvas.drawString(10 * mm, 10 * mm, 'REGISTER TESTE')
        canvas.showPage()
        canvas.save()
        self.pdf = base64.urlsafe_b64encode(pdf.getvalue()).decode().rstrip('=')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.registro.stop()
        self.pasta.cleanup()

    def pedir(self, caminho='/imprimir', origem=next(iter(ponte.ORIGENS)), pdf=None):
        conn = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request('POST', caminho, json.dumps({'pdf': self.pdf if pdf is None else pdf,
                                               'pedido': 'teste-pedido-unico-20261004'}),
                     {'Host': '127.0.0.1:17857', 'Origin': origem, 'Content-Type': 'application/json'})
        response = conn.getresponse()
        resultado = response.status, json.loads(response.read()), response.getheader('Access-Control-Allow-Origin')
        conn.close()
        return resultado

    def test_validar_nao_imprime_e_retorna_uma_etiqueta_com_tinta(self):
        with patch.object(ponte, 'imprimir') as impressao:
            status, resultado, origem = self.pedir('/validar')
        self.assertEqual(status, 200)
        self.assertEqual(resultado['altura_pontos'], 240)
        self.assertGreater(resultado['tinta_pontos'], 20)
        self.assertIn(origem, ponte.ORIGENS)
        impressao.assert_not_called()

    def test_reenvio_do_mesmo_pedido_imprime_so_uma_vez(self):
        with patch.object(ponte, 'imprimir', return_value={'impressora': 'POS-58', 'trabalho': 1}) as impressao:
            primeiro = self.pedir()
            segundo = self.pedir()
        self.assertEqual(primeiro, segundo)
        self.assertEqual(primeiro[1]['status'], 'enviada')
        impressao.assert_called_once()

    def test_origem_estranha_e_pdf_invalido_nao_imprimem(self):
        with patch.object(ponte, 'imprimir') as impressao:
            self.assertEqual(self.pedir(origem='https://outro.example')[0], 403)
            self.assertEqual(self.pedir(pdf='nao-e-um-pdf')[0], 400)
        impressao.assert_not_called()


if __name__ == '__main__':
    unittest.main()
