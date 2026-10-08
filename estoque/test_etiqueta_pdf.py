from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from .etiqueta_pdf import gerar_etiqueta_pdf


class EtiquetaPaginaTests(SimpleTestCase):
    def test_botao_do_sistema_abre_pagina_imprimivel_e_preserva_pdf(self):
        from django.test import RequestFactory
        from .views import etiqueta
        peca = SimpleNamespace(pk=1, nome='Farol', marca='Fiat', aplicacao='Tempra',
                              ano_inicial=1992, ano_final=1998, posicao='ESQUERDO',
                              codigo='REG000002')
        usuario = SimpleNamespace(is_authenticated=True, has_perms=lambda permissoes: True)
        fabrica = RequestFactory()
        with patch('estoque.views.get_object_or_404', return_value=peca), \
                patch('core.context_processors.ConfiguracaoEmpresa.objects') as empresas:
            empresas.only.return_value.first.return_value = None
            request = fabrica.get('/estoque/1/etiqueta/')
            request.user = usuario
            response = etiqueta(request, 1)
            self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
            self.assertContains(response, 'id="imprimir"')
            self.assertContains(response, 'data-etiqueta="')
            self.assertContains(response, 'id="impressao-status"')
            self.assertNotContains(response, 'imprimir-navegador')
            self.assertContains(response, 'css/etiqueta.css?v=')
            self.assertContains(response, 'js/etiqueta.js?v=')
            self.assertContains(response, 'REG000002')
            self.assertContains(response, '?formato=pdf')
            self.assertEqual(response['Cache-Control'], 'private, no-store')
            request = fabrica.get('/estoque/1/etiqueta/', {'formato': 'pdf'})
            request.user = usuario
            response = etiqueta(request, 1)
            self.assertEqual(response['Content-Type'], 'application/pdf')
            self.assertTrue(response.content.startswith(b'%PDF-'))


class EtiquetaPDFTests(SimpleTestCase):
    def test_bobina_58mm_avanca_uma_etiqueta_de_30mm(self):
        peca = SimpleNamespace(
            nome='Farol dianteiro', marca='Fiat', aplicacao='Tempra',
            ano_inicial=1992, ano_final=1998, posicao='ESQUERDO',
            codigo='REG000002',
        )
        real_canvas = canvas.Canvas
        with patch('estoque.etiqueta_pdf.canvas.Canvas') as fabrica:
            def criar(*args, **kwargs):
                from unittest.mock import Mock
                return Mock(wraps=real_canvas(*args, **kwargs))
            fabrica.side_effect = criar
            pdf = gerar_etiqueta_pdf(peca)
            self.assertEqual(fabrica.call_args.kwargs['pagesize'], (57 * mm, 30 * mm))
            self.assertTrue(pdf.startswith(b'%PDF-'))

    def test_orientacao_preserva_largura_e_altura_da_etiqueta(self):
        from io import BytesIO
        from unittest.mock import Mock
        impressao = Mock(wraps=canvas.Canvas(BytesIO(), pagesize=(57 * mm, 30 * mm)))
        peca = SimpleNamespace(nome='Farol', marca='', aplicacao='',
                              ano_inicial=None, ano_final=None, posicao='', codigo='REG000002')
        with patch('estoque.etiqueta_pdf.canvas.Canvas', return_value=impressao):
            gerar_etiqueta_pdf(peca)
        impressao.setPageRotation.assert_called_once_with(0)
        impressao.rotate.assert_called_once_with(180)
        impressao.showPage.assert_called_once_with()
        impressao.drawString.assert_any_call(4.5 * mm, 22.4 * mm, 'Farol')
        chamadas = impressao.drawString.call_args_list
        self.assertEqual(len(chamadas), 4)
        self.assertIn(' | Lado:', chamadas[2].args[2])
        self.assertTrue(all(chamadas[i].args[1] - chamadas[i+1].args[1] > 7.5 for i in range(3)))
