import ssl
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase, override_settings, Client
from django.urls import reverse
from django.conf import settings
from lxml import etree

from .models import ConfiguracaoFiscal, DocumentoFiscal, SequenciaFiscal, EventoFiscal, TentativaTransmissao
from .provedores import SefazDireta, requisitar
from .sefaz_sp import testar_conexao, consultar_status, endpoint, ENDPOINTS, ResultadoConexao
from .seguranca import ErroFiscal, ErroCertificadoFiscal, salvar_a1, contexto_tls
from .tests import CHAVE, certificado, empresa
from .xml import NFE


def retorno(codigo='107', ambiente='2', uf='35'):
    return (f'<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body>'
        f'<nfeResultMsg xmlns="{NFE}/wsdl/NFeStatusServico4"><retConsStatServ xmlns="{NFE}" versao="4.00">'
        f'<tpAmb>{ambiente}</tpAmb><verAplic>SP_NFE_PL_4</verAplic><cStat>{codigo}</cStat>'
        f'<xMotivo>Servico em Operacao</xMotivo><cUF>{uf}</cUF><dhRecbto>2026-10-05T12:00:00-03:00</dhRecbto>'
        '<tMed>1</tMed></retConsStatServ></nfeResultMsg></soap:Body></soap:Envelope>')


@override_settings(FISCAL_SECRET_KEY=CHAVE, FISCAL_ENABLED=False, FISCAL_ALLOW_PRODUCTION=False)
class ProtocoloSefazSpTests(SimpleTestCase):
    def setUp(self):
        self.config=ConfiguracaoFiscal(uf='SP')

    def test_status_soap_oficial_nfe_nfce_sem_assinatura_ou_emissao(self):
        for modelo in ('55','65'):
            with self.subTest(modelo=modelo), patch('fiscal.provedores.requisitar',return_value=retorno()) as enviar:
                r=consultar_status(self.config,modelo)
                self.assertEqual(r.status,'conectado');self.assertEqual(r.codigo,'107')
                args=enviar.call_args.args
                self.assertEqual(args[1],'homologacao');self.assertEqual(args[2],ENDPOINTS[modelo]['status'])
                root=etree.fromstring(args[3]);cons=root.find('.//{'+NFE+'}consStatServ')
                self.assertEqual(cons.get('versao'),'4.00')
                self.assertEqual([(etree.QName(e).localname,e.text) for e in cons], [('tpAmb','2'),('cUF','35'),('xServ','STATUS')])
                self.assertEqual(len(root.findall('.//{http://www.w3.org/2003/05/soap-envelope}Body')),1)
                self.assertTrue(args[4].endswith('/NFeStatusServico4/nfeStatusServicoNF"'))
                self.assertNotIn(b'Signature',args[3]);self.assertNotIn(b'enviNFe',args[3])

    def test_producao_bloqueada_mesmo_com_flags_liberadas(self):
        self.config.ambiente='producao'
        with override_settings(FISCAL_ALLOW_PRODUCTION=True,FISCAL_ENABLED=True),patch('fiscal.provedores.requisitar') as rede:
            for modelo in ('55','65'):
                for operacao in ENDPOINTS[modelo]:
                    with self.assertRaises(ErroFiscal):
                        endpoint(self.config,modelo,operacao,'producao')
                doc=SimpleNamespace(modelo=modelo,ambiente='producao')
                with self.assertRaises(ErroFiscal):SefazDireta().endpoint(self.config,doc,'emitir')
            rede.assert_not_called()

    def test_endpoint_personalizado_e_outra_uf_bloqueados(self):
        for url in ('https://nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx','https://hom.exemplo.gov.br/status'):
            self.config.endpoints={'homologacao':{'55':{'status':url}}}
            with self.assertRaises(ErroFiscal):endpoint(self.config,'55','status','homologacao')
        self.config.endpoints={};self.config.uf='RJ'
        with self.assertRaises(ErroFiscal):endpoint(self.config,'55','status','homologacao')

    def test_configuracao_ausente_e_certificado_ausente_sem_rede(self):
        with patch('fiscal.provedores.requisitar') as rede:
            self.assertEqual(testar_conexao(None,'55').status,'configuracao_ausente')
            self.assertEqual(testar_conexao(self.config,'55').status,'configuracao_ausente')
            with override_settings(FISCAL_SECRET_KEY=''):
                self.assertEqual(testar_conexao(self.config,'55').status,'configuracao_ausente')
            rede.assert_not_called()

    def test_certificado_corrompido_ou_vencido_sem_rede(self):
        from django.utils import timezone
        from datetime import timedelta
        self.config.certificado_criptografado=b'invalido';self.config.senha_a1_criptografada=b'senha-nao-ecoa'
        for dias in (-1,30):
            self.config.certificado_valido_ate=timezone.now()+timedelta(days=dias)
            with patch('fiscal.provedores.requisitar') as rede:
                r=testar_conexao(self.config,'55');self.assertEqual(r.status,'certificado_invalido')
                self.assertNotIn('senha-nao-ecoa',r.mensagem);rede.assert_not_called()

    def test_prevalidacao_a1_real_com_servico_simulado(self):
        dados,_=certificado();salvar_a1(self.config,dados,'senha-sintetica')
        with patch('fiscal.provedores.requisitar',return_value=retorno()):
            self.assertEqual(testar_conexao(self.config,'55').status,'conectado')

    def test_respostas_nao_confirmadas_nao_sao_conectado(self):
        for xml in ('<ret/>',retorno(ambiente='1'),retorno(uf='41'),retorno(codigo='100'),
                    '<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x/>'):
            with self.subTest(xml=xml[:25]),patch('fiscal.provedores.requisitar',return_value=xml):
                try:r=consultar_status(self.config,'55')
                except ErroFiscal:continue
                self.assertNotEqual(r.status,'conectado')

    def test_indisponibilidade_certificado_e_fault_sanitizados(self):
        for codigo,estado in [('108','erro_sefaz'),('109','erro_sefaz'),('280','certificado_invalido'),('999','erro_sefaz')]:
            xml=retorno(codigo).replace('Servico em Operacao','senha=segredo chave-privada-nao-ecoa')
            with patch('fiscal.provedores.requisitar',return_value=xml):
                r=consultar_status(self.config,'65');self.assertEqual(r.status,estado)
                self.assertNotIn('segredo',r.mensagem);self.assertNotIn('chave-privada',r.mensagem)
        xml='<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><s:Fault><s:Reason>senha=segredo</s:Reason></s:Fault></s:Body></s:Envelope>'
        with patch('fiscal.provedores.requisitar',return_value=xml):
            r=consultar_status(self.config,'55');self.assertEqual(r.status,'erro_sefaz');self.assertNotIn('segredo',r.mensagem)

    def test_erro_tls_certificado_classificado_sem_segredos(self):
        alerta=ssl.SSLError(1,'senha=segredo');alerta.reason='SSLV3_ALERT_BAD_CERTIFICATE'
        tls=Mock();tls.__enter__=Mock(return_value=Mock());tls.__exit__=Mock(return_value=False)
        with patch('fiscal.provedores.contexto_tls',return_value=tls),patch('fiscal.provedores.build_opener',return_value=Mock(open=Mock(side_effect=URLError(alerta)))):
            with self.assertRaises(ErroCertificadoFiscal) as erro:
                requisitar(self.config,'homologacao',ENDPOINTS['55']['status'],b'<x/>')
        self.assertNotIn('segredo',str(erro.exception))

    def test_tls_carrega_a1_e_verifica_servidor(self):
        dados,_=certificado();salvar_a1(self.config,dados,'senha-sintetica')
        # O sandbox Windows não acessa diretórios com ACL privada de mkdtemp.
        # Substituir apenas o diretório; certificado, chave e SSL continuam reais.
        base=(Path(settings.BASE_DIR)/'tmp/fiscal').resolve()
        pasta=base/'tls-certificado-sintetico';pasta.mkdir(exist_ok=True)
        temporario=Mock();temporario.__enter__=Mock(return_value=str(pasta));temporario.__exit__=Mock(return_value=False)
        try:
            with patch('fiscal.seguranca.TemporaryDirectory',return_value=temporario),contexto_tls(self.config) as tls:
                self.assertEqual(tls.verify_mode,ssl.CERT_REQUIRED)
                self.assertTrue(tls.check_hostname)
                self.assertGreaterEqual(tls.minimum_version,ssl.TLSVersion.TLSv1_2)
                self.assertIn(b'BEGIN ENCRYPTED PRIVATE KEY',(pasta/'key').read_bytes())
                self.assertNotIn(b'senha-sintetica',(pasta/'key').read_bytes())
        finally:
            assert pasta.resolve().is_relative_to(base)
            for nome in ('cert','key'):(pasta/nome).unlink(missing_ok=True)
            pasta.rmdir()


@override_settings(FISCAL_SECRET_KEY=CHAVE,FISCAL_ENABLED=False)
class AcaoConexaoSefazTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('configurador-conexao')
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='fiscal',codename='configurar_fiscal'))
        self.client.force_login(self.user)
        self.rota=reverse('fiscal:testar_conexao_sefaz')

    def test_get_nao_consulta_e_permissao_especifica_obrigatoria(self):
        with patch('fiscal.sefaz_sp.testar_conexao') as testar:
            self.assertEqual(self.client.get(self.rota).status_code,405)
            outro=get_user_model().objects.create_user('sem-configurar-conexao');self.client.force_login(outro)
            self.assertEqual(self.client.post(self.rota,{'modelo':'55'}).status_code,403)
            testar.assert_not_called()

    def test_csrf_obrigatorio(self):
        cliente=Client(enforce_csrf_checks=True);cliente.force_login(self.user)
        self.assertEqual(cliente.post(self.rota,{'modelo':'55'}).status_code,403)

    def test_configuracao_ausente_mostra_resultado(self):
        with patch('fiscal.provedores.requisitar') as rede:
            response=self.client.post(self.rota,{'modelo':'55'},follow=True)
        self.assertContains(response,'Configuração ausente');self.assertContains(response,'Testar conexão SEFAZ')
        rede.assert_not_called();self.assertFalse(ConfiguracaoFiscal.objects.exists())

    def test_botao_nao_emite_nem_reserva_documentos(self):
        config=empresa();dados,_=certificado();salvar_a1(config,dados,'senha-sintetica');config.save()
        with patch('fiscal.provedores.requisitar',return_value=retorno()) as rede,patch('fiscal.services.transmitir') as emitir:
            response=self.client.post(self.rota,{'modelo':'65'},follow=True)
        self.assertContains(response,'Conectado');self.assertEqual(rede.call_count,1);emitir.assert_not_called()
        for model in (DocumentoFiscal,SequenciaFiscal,EventoFiscal,TentativaTransmissao):
            self.assertEqual(model.objects.count(),0)
        config.refresh_from_db();self.assertEqual(config.ambiente,'homologacao')

    def test_erro_rede_nao_expoe_excecao(self):
        config=empresa();dados,_=certificado();salvar_a1(config,dados,'senha-sintetica');config.save()
        with patch('fiscal.provedores.requisitar',side_effect=RuntimeError('senha-sintetica private key segredo')):
            response=self.client.post(self.rota,{'modelo':'55'},follow=True)
        self.assertContains(response,'Erro de comunicação');self.assertNotContains(response,'senha-sintetica')
