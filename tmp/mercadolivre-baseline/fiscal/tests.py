import base64
import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, Mock

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connections
from django.test import TestCase, SimpleTestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from lxml import etree

from caixa.models import MovimentoCaixa
from caixa.services import abrir
from clientes.models import Cliente
from comercial.models import Servico, Documento, ItemDocumento
from estoque.models import Peca, Categoria
from vendas.models import FormaPagamento, Venda
from vendas.services import finalizar
from . import services
from .forms import ConfiguracaoForm, SequenciaForm, ProdutoForm, ServicoForm
from .models import ConfiguracaoFiscal, DocumentoFiscal, SequenciaFiscal, ParametroProduto, ParametroServico, EventoFiscal, Status
from .provedores import Resultado, SefazDireta
from .seguranca import ErroFiscal, criptografar, descriptografar, salvar_a1, assinatura_xml, xml_seguro, validar_url, resposta_sanitizada
from .xml import gerar_dps, gerar_nfe, chave_nfe

CHAVE=Fernet.generate_key().decode()


def empresa():
    return ConfiguracaoFiscal.objects.create(ativa=True,cnpj='11222333000181',razao_social='EMPRESA TESTE',
        uf='SP',municipio_ibge='3550308',municipio='Sao Paulo',logradouro='Rua Teste',numero='1',
        bairro='Centro',cep='01001000',ie='110042490114',parametros_nfse={'municipio_conveniado':True})


def certificado():
    chave=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    nome=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'CERTIFICADO SINTETICO DE TESTE')])
    cert=(x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(timezone.now()-timedelta(days=1))
          .not_valid_after(timezone.now()+timedelta(days=30)).sign(chave,hashes.SHA256()))
    dados=pkcs12.serialize_key_and_certificates(b'teste',chave,cert,None,serialization.BestAvailableEncryption(b'senha-sintetica'))
    return dados,cert


@override_settings(FISCAL_SECRET_KEY=CHAVE)
class SegurancaTests(SimpleTestCase):
    def test_parametros_json_vazios_sao_objetos(self):
        for classe,campo,metodo in ((ProdutoForm,'tributos_adicionais','clean_tributos_adicionais'),
                                   (ServicoForm,'parametros','clean_parametros')):
            form=classe();form.cleaned_data={campo:None}
            self.assertEqual(getattr(form,metodo)(),{})
            form.cleaned_data={campo:[]}
            from django.core.exceptions import ValidationError
            with self.assertRaises(ValidationError):getattr(form,metodo)()

    def test_segredo_encriptado_e_chave_independente(self):
        cifrado=criptografar('senha-sintetica')
        self.assertNotIn(b'senha-sintetica',cifrado)
        self.assertEqual(descriptografar(cifrado),b'senha-sintetica')
        with override_settings(FISCAL_SECRET_KEY=Fernet.generate_key().decode()), self.assertRaises(ErroFiscal):
            descriptografar(cifrado)

    def test_sem_chave_nao_usa_secret_key_django(self):
        with override_settings(FISCAL_SECRET_KEY=''),self.assertRaises(ErroFiscal):criptografar('segredo')

    def test_certificado_a1_e_assinatura_verificavel(self):
        dados,cert=certificado();config=ConfiguracaoFiscal()
        salvar_a1(config,dados,'senha-sintetica')
        self.assertNotEqual(bytes(config.certificado_criptografado),dados)
        self.assertNotIn(b'senha-sintetica',bytes(config.senha_a1_criptografada))
        raiz=etree.fromstring(b'<NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe Id="NFe123"><x>TESTE</x></infNFe></NFe>')
        assinatura_xml(raiz,'infNFe',config)
        raiz=xml_seguro(etree.tostring(raiz))
        info=raiz.find('.//{*}SignedInfo');sig=raiz.find('.//{*}SignatureValue').text
        cert.public_key().verify(base64.b64decode(sig),etree.tostring(info,method='c14n'),padding.PKCS1v15(),hashes.SHA1())
        import hashlib
        alvo=raiz.find('.//{*}infNFe')
        self.assertEqual(base64.b64decode(raiz.find('.//{*}DigestValue').text),hashlib.sha1(etree.tostring(alvo,method='c14n')).digest())

    def test_senha_invalida_nao_vaza(self):
        dados,_=certificado()
        with self.assertRaises(ErroFiscal) as erro:salvar_a1(ConfiguracaoFiscal(),dados,'senha-ultrassecreta')
        self.assertNotIn('senha-ultrassecreta',str(erro.exception))

    def test_bloqueia_xxe_e_endpoints_inseguros(self):
        with self.assertRaises(ErroFiscal):xml_seguro('<!DOCTYPE a [<!ENTITY b SYSTEM "file:///etc/passwd">]><a>&b;</a>')
        for url in ('http://nfe.fazenda.sp.gov.br','https://127.0.0.1','https://nfe.fazenda.sp.gov.br@evil.example'):
            with self.assertRaises(ErroFiscal):validar_url(url)
        with self.assertRaises(ErroFiscal):validar_url('https://nfe.fazenda.sp.gov.br','homologacao')

    def test_resposta_sem_certificado(self):
        self.assertNotIn('CERTIFICADO',resposta_sanitizada('<X509Certificate>CERTIFICADO</X509Certificate>'))


@override_settings(FISCAL_ENABLED=True,FISCAL_ALLOW_PRODUCTION=False,FISCAL_SECRET_KEY=CHAVE)
class FiscalTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser('fiscal-teste',password='teste')
        self.config=empresa()
        self.peca=Peca.objects.create(nome='Peca fiscal',categoria=Categoria.objects.create(nome='Categoria fiscal teste'),preco_venda=100,quantidade=10)
        self.servico=Servico.objects.create(nome='Instalacao',valor_padrao=50)
        self.cliente=Cliente.objects.create(nome='Cliente',documento='12345678909')
        self.caixa=abrir(self.user,'0')
        self.forma=FormaPagamento.objects.get_or_create(nome='Dinheiro', defaults={'dinheiro':True})[0]
        self.p=ParametroProduto.objects.create(peca=self.peca,ncm='87089990',cfop='5102')
        self.s=ParametroServico.objects.create(servico=self.servico,item_lista_lc116='14.01',codigo_tributacao_nacional='140101',municipio_incidencia='3550308')
        self.venda=finalizar(self.user,uuid.uuid4(),{str(self.peca.pk):{'quantidade':1,'preco':'100'},
            f's:{self.servico.pk}':{'quantidade':1,'preco':'50'}},[{'forma':self.forma.pk,'valor':'150'}],cliente_id=self.cliente.pk,desconto=15)
        self.client.force_login(self.user)

    def nota(self,modelo='65'):
        return services.solicitar(self.user,venda_id=self.venda.pk,modelo=modelo)

    def preparado(self):
        doc=self.nota();doc.xml_assinado='<NFe/>';doc.save(update_fields=['xml_assinado']);return doc

    def negocios(self):
        self.venda.refresh_from_db();self.peca.refresh_from_db()
        return (self.venda.status,self.venda.total,self.peca.quantidade,MovimentoCaixa.objects.count(),list(self.venda.pagamentos.values_list('valor','recebido','troco')))

    def test_desativado_por_flag_nao_cria_nota(self):
        with override_settings(FISCAL_ENABLED=False),self.assertRaises(ErroFiscal):self.nota()
        self.assertFalse(DocumentoFiscal.objects.exists())

    def test_desativado_por_configuracao(self):
        self.config.ativa=False;self.config.save()
        with self.assertRaises(ErroFiscal):self.nota()

    def test_producao_bloqueada(self):
        self.config.ambiente='producao';self.config.homologacao_validada=True;self.config.producao_validada=True;self.config.save()
        with self.assertRaises(ErroFiscal):self.nota()

    def test_separacao_mercadorias_servicos_preserva_total_rateado(self):
        a=self.nota();b=self.nota('nfse')
        self.assertEqual(a.total,Decimal('90'));self.assertEqual(b.total,Decimal('45'))
        self.assertEqual(a.total+b.total,self.venda.total)
        self.assertEqual(len(a.snapshot['itens']),1)

    def test_idempotencia_e_numero_reservado_uma_vez(self):
        a=self.nota();b=self.nota()
        self.assertEqual(a.pk,b.pk);self.assertEqual(SequenciaFiscal.objects.get().proximo_numero,2)
        with self.assertRaises(ErroFiscal):self.nota('55')

    def test_os_convertida_usa_mesma_venda_sem_duplicar(self):
        ordem=Documento.objects.create(tipo='os',status='convertido',cliente=self.cliente,criado_por=self.user,venda=self.venda)
        a=services.solicitar(self.user,os_id=ordem.pk,modelo='65');b=self.nota()
        self.assertEqual(a.pk,b.pk);self.assertEqual(a.ordem_servico_id,ordem.pk)

    def test_os_sem_venda_rateia_sem_escrever_financeiro(self):
        ordem=Documento.objects.create(tipo='os',status='finalizada',cliente=self.cliente,criado_por=self.user,desconto=15)
        ItemDocumento.objects.create(documento=ordem,peca=self.peca,descricao='Peca',quantidade=1,preco=100)
        ItemDocumento.objects.create(documento=ordem,servico=self.servico,descricao='Instalacao',quantidade=1,preco=50)
        antes=self.negocios()
        a=services.solicitar(self.user,os_id=ordem.pk,modelo='65');b=services.solicitar(self.user,os_id=ordem.pk,modelo='nfse')
        self.assertEqual(a.total+b.total,135);self.assertEqual(self.negocios(),antes)

    def test_rejeicao_nao_altera_negocios(self):
        doc=self.preparado();antes=self.negocios()
        with patch('fiscal.services.provedor') as p:
            p.return_value.emitir.return_value=Resultado('rejeitada','999','Rejeicao de teste',resposta='<cStat>999</cStat>')
            doc=services.transmitir(self.user,doc.pk)
        self.assertEqual(doc.status,Status.REJEITADA);self.assertEqual(self.negocios(),antes)
        self.assertEqual(doc.tentativas.count(),1)

    def test_timeout_nao_reemite_ate_consulta(self):
        doc=self.preparado();antes=self.negocios()
        with patch('fiscal.services.provedor') as p:
            p.return_value.emitir.side_effect=RuntimeError('senha-secreta-certificado-na-excecao')
            doc=services.transmitir(self.user,doc.pk)
            with self.assertRaises(ErroFiscal):services.transmitir(self.user,doc.pk)
            self.assertEqual(p.return_value.emitir.call_count,1)
        self.assertTrue(doc.transmissao_incerta);self.assertEqual(self.negocios(),antes)
        self.assertNotIn('senha-secreta',doc.tentativas.first().mensagem)
        with patch('fiscal.services.provedor') as p:
            p.return_value.consultar.return_value=Resultado('nao_solicitada','217','Nao localizada')
            doc=services.consultar(self.user,doc.pk)
        self.assertFalse(doc.transmissao_incerta);self.assertEqual(doc.numero,1)

    def test_autorizada_nao_transmite_de_novo(self):
        doc=self.preparado()
        with patch('fiscal.services.provedor') as p:
            p.return_value.emitir.return_value=Resultado('autorizada','100','Autorizada','123456',xml='<nfeProc/>')
            services.transmitir(self.user,doc.pk);services.transmitir(self.user,doc.pk)
            self.assertEqual(p.return_value.emitir.call_count,1)

    def test_cancelamento_fiscal_nao_cancela_venda(self):
        doc=self.preparado();doc.status='autorizada';doc.protocolo='123';doc.save()
        antes=self.negocios()
        ev=services.solicitar_cancelamento(self.user,doc.pk,'Cancelamento fiscal de teste')
        self.assertEqual(ev.pk,services.solicitar_cancelamento(self.user,doc.pk,'Outra justificativa teste').pk)
        with patch('fiscal.services.provedor') as p:
            p.return_value.cancelar.return_value=Resultado('cancelada','135','Cancelada','999')
            services.transmitir_evento(self.user,ev.pk)
        doc.refresh_from_db();self.assertEqual(doc.status,Status.CANCELADA);self.assertEqual(self.negocios(),antes)

    def test_inutilizacao_nao_aceita_numero_reservado(self):
        self.nota()
        with self.assertRaises(ErroFiscal):services.solicitar_inutilizacao(self.user,'65',1,1,2,timezone.localdate().year,'Teste de inutilizacao fiscal')
        ev=services.solicitar_inutilizacao(self.user,'65',1,10,12,timezone.localdate().year,'Teste de inutilizacao fiscal')
        self.assertEqual(ev.pk,services.solicitar_inutilizacao(self.user,'65',1,10,12,timezone.localdate().year,'Teste de inutilizacao fiscal').pk)

    def test_numero_nao_retrocede(self):
        self.nota();form=SequenciaForm(data={'modelo':'65','ambiente':'homologacao','serie':1,'proximo_numero':1})
        self.assertTrue(form.is_valid(),form.errors)
        with self.assertRaises(ErroFiscal):form.save()

    def test_snapshot_de_empresa_e_valores_preservado(self):
        doc=self.nota();self.config.razao_social='EMPRESA ALTERADA';self.config.save()
        self.p.ncm='12345678';self.p.save();antes=doc.total
        doc=services.atualizar_parametros(self.user,doc.pk)
        self.assertEqual(doc.snapshot['empresa']['razao_social'],'EMPRESA TESTE')
        self.assertEqual(doc.total,antes);self.assertEqual(doc.numero,1)
        self.assertEqual(doc.snapshot['itens'][0]['fiscal']['ncm'],'12345678')

    def test_schemas_ausentes_bloqueiam_antes_da_rede(self):
        doc=self.nota('nfse');dados,_=certificado();salvar_a1(self.config,dados,'senha-sintetica');self.config.save()
        with override_settings(FISCAL_SCHEMA_DIR='tmp/fiscal/esquemas-nao-instalados'),patch('fiscal.services.provedor') as p:
            doc=services.transmitir(self.user,doc.pk);p.assert_not_called()
        self.assertEqual(doc.status,Status.ERRO_TECNICO);self.assertFalse(doc.transmissao_incerta)

    def test_dps_validado_contra_schema_oficial(self):
        dados,_=certificado();salvar_a1(self.config,dados,'senha-sintetica');self.config.save()
        xml,ident,_=gerar_dps(self.nota('nfse'),self.config)
        self.assertTrue(ident.startswith('DPS35503082'))
        self.assertIn('<Signature',xml)

    def test_nfce_qr_e_xml_validado_contra_schema_oficial(self):
        dados,_=certificado();salvar_a1(self.config,dados,'senha-sintetica')
        self.config.csc_id='1';self.config.csc_criptografado=criptografar('csc-sintetico')
        self.config.qr_code_versao='2'
        self.config.endpoints={'homologacao':{'65':{
            'qr_code':'https://www.homologacao.nfce.fazenda.sp.gov.br/qrcode',
            'consulta_publica':'https://www.homologacao.nfce.fazenda.sp.gov.br/consulta'}}}
        xml,chave,qr=gerar_nfe(self.nota(),self.config)
        self.assertEqual(len(chave),44);self.assertIn('|2|2|1|',qr)
        self.assertNotIn('csc-sintetico',xml)

    def test_nfe_validado_contra_schema_oficial(self):
        dados,_=certificado();salvar_a1(self.config,dados,'senha-sintetica')
        doc=services.solicitar(self.user,venda_id=self.venda.pk,modelo='55',destinatario={
            'logradouro':'Rua','numero':'1','bairro':'Centro','municipio_ibge':'3550308','municipio':'Sao Paulo','uf':'SP','cep':'01001000'})
        xml,chave,qr=gerar_nfe(doc,self.config)
        self.assertEqual(qr,'');self.assertIn('<NFe',xml)

    def test_nfce_v3_e_contingencia_preservam_negocio(self):
        dados,_=certificado();salvar_a1(self.config,dados,'senha-sintetica')
        self.config.endpoints={'homologacao':{'65':{
            'qr_code':'https://www.homologacao.nfce.fazenda.sp.gov.br/qrcode',
            'consulta_publica':'https://www.homologacao.nfce.fazenda.sp.gov.br/consulta'}}}
        self.config.save();doc=self.nota();antes=self.negocios()
        xml,chave,qr=gerar_nfe(doc,self.config)
        self.assertTrue(qr.endswith('|3|2'))
        doc=services.ativar_contingencia(self.user,doc.pk,'Indisponibilidade de teste da SEFAZ')
        self.assertEqual(doc.status,Status.CONTINGENCIA);self.assertEqual(doc.chave_acesso[34],'9')
        self.assertIn('<tpEmis>9</tpEmis>',doc.xml_assinado);self.assertIn('|3|2|',doc.qr_code)
        self.assertEqual(self.negocios(),antes)

    def test_cancelamento_nfse_validado_sem_rede(self):
        from .provedores import NfseNacionalDireta
        dados,_=certificado();salvar_a1(self.config,dados,'senha-sintetica')
        doc=self.nota('nfse');doc.status='autorizada';doc.protocolo='123';doc.chave_acesso='1'*50;doc.save()
        ev=services.solicitar_cancelamento(self.user,doc.pk,'Cancelamento de homologacao')
        with patch('fiscal.provedores.requisitar',return_value='{}') as enviar:
            NfseNacionalDireta().cancelar(self.config,doc,ev)
        enviar.assert_called_once()

    def test_resposta_nfse_vazia_nao_libera_retransmissao(self):
        from .provedores import NfseNacionalDireta
        with self.assertRaises(ErroFiscal):
            NfseNacionalDireta().interpretar('{}',self.nota('nfse'))

    def test_evento_local_nao_pode_ser_transmitido(self):
        ev=EventoFiscal.objects.create(configuracao=self.config,operador=self.user,tipo='contingencia',
            modelo='65',ambiente='homologacao',serie=1,status=Status.CONTINGENCIA)
        with patch('fiscal.services.provedor') as p,self.assertRaises(ErroFiscal):
            services.transmitir_evento(self.user,ev.pk)
        p.assert_not_called()

    def test_evento_cancelamento_nfe_validado_sem_rede(self):
        dados,_=certificado();salvar_a1(self.config,dados,'senha-sintetica')
        doc=self.preparado();doc.status='autorizada';doc.protocolo='135260000000001';doc.save()
        ev=services.solicitar_cancelamento(self.user,doc.pk,'Cancelamento de homologacao')
        with patch.object(SefazDireta,'enviar',return_value=Resultado('cancelada')) as enviar:
            SefazDireta().cancelar(self.config,doc,ev)
        enviar.assert_called_once()

    def test_inutilizacao_nfe_validada_sem_rede(self):
        dados,_=certificado();salvar_a1(self.config,dados,'senha-sintetica')
        ev=services.solicitar_inutilizacao(self.user,'55',1,10,12,timezone.localdate().year,'Teste de inutilizacao fiscal')
        with patch.object(SefazDireta,'enviar',return_value=Resultado('autorizada','102',protocolo='135260000000001')) as enviar:
            SefazDireta().inutilizar(self.config,ev)
        enviar.assert_called_once()

    def test_permissoes_nao_fiscais_nao_emitem(self):
        outro=get_user_model().objects.create_user('sem-fiscal')
        with self.assertRaises(PermissionDenied):services.solicitar(outro,venda_id=self.venda.pk)
        self.client.force_login(outro)
        for rota in ('lista','configuracao','solicitar'):
            self.assertEqual(self.client.get(reverse('fiscal:'+rota)).status_code,403)

    def test_xml_consulta_e_get_sem_efeito(self):
        doc=self.preparado();outro=get_user_model().objects.create_user('consulta-fiscal')
        outro.user_permissions.add(Permission.objects.get(content_type__app_label='fiscal',codename='consultar_fiscal'))
        self.client.force_login(outro)
        self.assertEqual(self.client.get(reverse('fiscal:xml',args=[doc.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse('fiscal:acao',args=[doc.pk,'transmitir'])).status_code,405)
        self.assertEqual(self.client.post(reverse('fiscal:acao',args=[doc.pk,'transmitir'])).status_code,403)

    def test_interfaces_e_auxiliar(self):
        doc=self.nota()
        for rota,args in [('lista',[]),('nfe',[]),('nfce',[]),('nfse',[]),('pendentes',[]),('documentos',[]),
            ('eventos',[]),('configuracao',[]),('detalhe',[doc.pk]),('parametros',['produtos']),('parametros',['servicos'])]:
            response=self.client.get(reverse('fiscal:'+rota,args=args));self.assertEqual(response.status_code,200)
        self.assertTrue(self.client.get(reverse('fiscal:auxiliar',args=[doc.pk])).content.startswith(b'%PDF'))
        self.assertContains(self.client.get(reverse('fiscal:lista')),'Notas fiscais')

    def test_sefaz_chave_diferente_nao_autoriza(self):
        doc=self.preparado()
        xml='<ret><protNFe><infProt><chNFe>'+('1'*44)+'</chNFe><cStat>100</cStat><nProt>123</nProt></infProt></protNFe></ret>'
        with self.assertRaises(ErroFiscal):SefazDireta().interpretar(xml,doc)

    def test_resposta_sefaz_sem_situacao_nao_libera_retransmissao(self):
        with self.assertRaises(ErroFiscal):SefazDireta().interpretar('<ret/>',self.preparado())

    def test_consulta_cancelamento_usa_chave_em_vez_de_recibo_antigo(self):
        doc=self.preparado();doc.status=Status.CANCELAMENTO_PENDENTE;doc.recibo='123'
        with patch.object(SefazDireta,'enviar',return_value=Resultado('autorizada','100')) as enviar:
            SefazDireta().consultar(self.config,doc)
        self.assertEqual(enviar.call_args.args[2],'consultar')

    def test_cancelamento_incerto_so_libera_apos_consulta(self):
        doc=self.preparado();doc.status=Status.AUTORIZADA;doc.protocolo='123';doc.save()
        ev=services.solicitar_cancelamento(self.user,doc.pk,'Cancelamento de homologacao')
        ev.status=Status.ERRO_TECNICO;ev.save()
        with patch('fiscal.services.provedor',return_value=Mock(consultar=Mock(return_value=Resultado(Status.AUTORIZADA,'100',protocolo='123')))):
            ev=services.consultar_evento(self.user,ev.pk)
        self.assertEqual(ev.status,Status.PENDENTE)


@override_settings(FISCAL_ENABLED=True)
class ConcorrenciaFiscalTests(TransactionTestCase):
    def test_duas_solicitacoes_simultaneas_reservam_uma_nota(self):
        config=empresa();user=get_user_model().objects.create_superuser('concorrencia-fiscal',password='teste')
        caixa=abrir(user,0);p=Peca.objects.create(nome='Teste',categoria=Categoria.objects.create(nome='Categoria fiscal teste'),preco_venda=10,quantidade=2)
        ParametroProduto.objects.create(peca=p,ncm='87089990',cfop='5102')
        v=finalizar(user,uuid.uuid4(),{str(p.pk):{'quantidade':1,'preco':'10'}},[{'forma':FormaPagamento.objects.get_or_create(nome='Dinheiro', defaults={'dinheiro':True})[0].pk,'valor':'10'}])
        def pedir():
            close_old_connections()
            try:return services.solicitar(get_user_model().objects.get(pk=user.pk),venda_id=v.pk,modelo='65').pk
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(lambda _:pedir(),range(2)))
        self.assertEqual(ids[0],ids[1]);self.assertEqual(DocumentoFiscal.objects.count(),1)
        self.assertEqual(SequenciaFiscal.objects.get().proximo_numero,2)
