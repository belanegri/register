"""Adaptadores diretos SEFAZ (SOAP 1.2) e SEFIN Nacional (mTLS/JSON)."""
import base64
import gzip
import io
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

from lxml import etree
from django.utils import timezone

from .seguranca import ErroFiscal, contexto_tls, validar_url, xml_seguro
from .xml import NFE, NFSE, UFS, el, campos, validar_schema, assinatura_xml


@dataclass
class Resultado:
    status: str
    codigo: str = ''
    mensagem: str = ''
    protocolo: str = ''
    recibo: str = ''
    chave: str = ''
    xml: str = ''
    resposta: str = ''


class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ErroFiscal('O serviço fiscal retornou um redirecionamento não permitido.')


def requisitar(config, ambiente, url, dados=None, content_type='application/json', metodo=None, binario=False):
    validar_url(url, ambiente)
    try:
        with contexto_tls(config) as tls:
            opener = build_opener(ProxyHandler({}), HTTPSHandler(context=tls), SemRedirecionamento())
            request = Request(url, data=dados, method=metodo, headers={'Content-Type':content_type, 'Accept':'application/json, application/xml', 'User-Agent':'REGISTER-fiscal/1'})
            try:
                resposta = opener.open(request, timeout=30)
            except HTTPError as erro:
                if erro.code in (400, 404, 409, 422):
                    resposta = erro
                else:
                    raise ErroFiscal('O serviço fiscal não confirmou a operação. Consulte antes de retransmitir.') from None
            with resposta:
                conteudo = resposta.read(5*1024*1024+1)
            if len(conteudo)>5*1024*1024:
                raise ErroFiscal('Resposta fiscal excede o limite permitido.')
            return conteudo if binario else conteudo.decode('utf-8-sig')
    except (URLError, OSError, UnicodeError):
        raise ErroFiscal('Falha de comunicação fiscal. Consulte a situação antes de retransmitir.') from None


def texto(raiz, nome):
    valores = raiz.xpath(f'.//*[local-name()="{nome}"]/text()')
    return valores[-1] if valores else ''


class SefazDireta:
    SERVICOS = {'emitir':('NFeAutorizacao4','nfeAutorizacaoLote'),
                'consultar':('NFeConsultaProtocolo4','nfeConsultaNF'),
                'recibo':('NFeRetAutorizacao4','nfeRetAutorizacaoLote'),
                'cancelar':('NFeRecepcaoEvento4','nfeRecepcaoEvento'),
                'inutilizar':('NFeInutilizacao4','nfeInutilizacaoNF')}

    def endpoint(self, config, doc, operacao):
        custom = config.endpoints.get(doc.ambiente, {}).get(doc.modelo, {}).get(operacao)
        if custom:
            return validar_url(custom, doc.ambiente)
        if config.uf != 'SP':
            raise ErroFiscal('Configure os serviços oficiais da UF/autorizador desta instalação.')
        sub = 'nfce' if doc.modelo=='65' else 'nfe'
        host = ('homologacao.' if doc.ambiente=='homologacao' else '') + sub+'.fazenda.sp.gov.br'
        return f'https://{host}/ws/{self.SERVICOS[operacao][0]}.asmx'

    def enviar(self, config, doc, operacao, payload):
        servico, metodo = self.SERVICOS[operacao]
        ns='http://www.w3.org/2003/05/soap-envelope'
        soap=etree.Element(f'{{{ns}}}Envelope',nsmap={'soap':ns})
        body=etree.SubElement(soap,f'{{{ns}}}Body')
        mensagem=etree.SubElement(body,f'{{{NFE}/wsdl/{servico}}}nfeDadosMsg')
        mensagem.append(payload)
        resultado = requisitar(config,doc.ambiente,self.endpoint(config,doc,operacao),
            etree.tostring(soap,encoding='utf-8',xml_declaration=True),
            f'application/soap+xml; charset=utf-8; action="{NFE}/wsdl/{servico}/{metodo}"')
        return self.interpretar(resultado,doc)

    def interpretar(self, resposta, doc):
        raiz=xml_seguro(resposta)
        if raiz.xpath('.//*[local-name()="Fault"]'):
            raise ErroFiscal('O serviço SEFAZ retornou falha SOAP. Consulte a situação.')
        protocolo=raiz.find('.//{*}infProt')
        evento=raiz.find('.//{*}retEvento/{*}infEvento')
        alvo = protocolo if protocolo is not None else (evento if evento is not None else raiz)
        codigo=texto(alvo,'cStat'); chave=texto(alvo,'chNFe')
        if not codigo.isdigit():raise ErroFiscal('Resposta SEFAZ sem situação fiscal confirmada.')
        if codigo in ('100','150','101','135','155') and not chave:
            raise ErroFiscal('Resposta SEFAZ sem a chave do documento.')
        if chave and chave != doc.chave_acesso:
            raise ErroFiscal('A resposta SEFAZ não corresponde à chave solicitada.')
        status = ('autorizada' if codigo in ('100','150') else 'cancelada' if codigo in ('101','135','155')
                  else 'pendente' if codigo in ('103','105') else 'nao_solicitada' if codigo=='217'
                  else 'rejeitada')
        xml=''
        if status=='autorizada':
            prot=raiz.find('.//{*}protNFe')
            if not texto(alvo,'nProt') or prot is None:
                raise ErroFiscal('Autorização sem protocolo válido.')
            proc=etree.Element(f'{{{NFE}}}nfeProc',nsmap={None:NFE},versao='4.00')
            proc.append(xml_seguro(doc.xml_assinado));proc.append(prot)
            xml=etree.tostring(proc,encoding='unicode')
        return Resultado(status,codigo,texto(alvo,'xMotivo'),texto(alvo,'nProt'),texto(raiz,'nRec'),chave,xml,resposta)

    def emitir(self, config, doc):
        raiz=etree.Element(f'{{{NFE}}}enviNFe',nsmap={None:NFE},versao='4.00')
        campos(raiz, {'idLote':doc.pk,'indSinc':'1'})
        raiz.append(xml_seguro(doc.xml_assinado))
        validar_schema(raiz,'enviNFe_v4.00.xsd')
        return self.enviar(config,doc,'emitir',raiz)

    def consultar(self, config, doc):
        if doc.recibo and doc.status not in ('autorizada','cancelamento_pendente','cancelada'):
            raiz=etree.Element(f'{{{NFE}}}consReciNFe',nsmap={None:NFE},versao='4.00')
            campos(raiz, {'tpAmb':'2' if doc.ambiente=='homologacao' else '1','nRec':doc.recibo})
            return self.enviar(config,doc,'recibo',raiz)
        raiz=etree.Element(f'{{{NFE}}}consSitNFe',nsmap={None:NFE},versao='4.00')
        campos(raiz, {'tpAmb':'2' if doc.ambiente=='homologacao' else '1','xServ':'CONSULTAR','chNFe':doc.chave_acesso})
        return self.enviar(config,doc,'consultar',raiz)

    def cancelar(self, config, doc, evento):
        raiz=etree.Element(f'{{{NFE}}}envEvento',nsmap={None:NFE},versao='1.00');el(raiz,'idLote',evento.pk)
        ev=el(raiz,'evento',versao='1.00')
        inf=el(ev,'infEvento',Id='ID110111'+doc.chave_acesso+'01')
        campos(inf, {'cOrgao':UFS[doc.snapshot['empresa']['uf']], 'tpAmb':'2' if doc.ambiente=='homologacao' else '1',
            'CNPJ':doc.snapshot['empresa']['cnpj'],'chNFe':doc.chave_acesso,
            'dhEvento':timezone.localtime(evento.criado_em).isoformat(timespec='seconds'),'tpEvento':'110111','nSeqEvento':'1','verEvento':'1.00'})
        campos(el(inf,'detEvento',versao='1.00'), {'descEvento':'Cancelamento','nProt':doc.protocolo,'xJust':evento.justificativa})
        assinatura_xml(ev,'infEvento',config);validar_schema(raiz,'envEventoCancNFe_v1.00.xsd')
        evento.xml=etree.tostring(raiz,encoding='unicode');evento.save(update_fields=['xml'])
        return self.enviar(config,doc,'cancelar',raiz)

    def inutilizar(self, config, evento):
        raiz=etree.Element(f'{{{NFE}}}inutNFe',nsmap={None:NFE},versao='4.00')
        ident=f'ID{UFS[config.uf]}{evento.ano%100:02d}{config.cnpj}{evento.modelo}{evento.serie:03d}{evento.numero_inicial:09d}{evento.numero_final:09d}'
        inf=el(raiz,'infInut',Id=ident)
        campos(inf, {'tpAmb':'2' if evento.ambiente=='homologacao' else '1','xServ':'INUTILIZAR','cUF':UFS[config.uf],
            'ano':f'{evento.ano%100:02d}','CNPJ':config.cnpj,'mod':evento.modelo,'serie':evento.serie,
            'nNFIni':evento.numero_inicial,'nNFFin':evento.numero_final,'xJust':evento.justificativa})
        assinatura_xml(raiz,'infInut',config);validar_schema(raiz,'inutNFe_v4.00.xsd')
        evento.xml=etree.tostring(raiz,encoding='unicode');evento.save(update_fields=['xml'])
        r=self.enviar(config,evento,'inutilizar',raiz)
        if r.codigo=='102':
            if not r.protocolo:raise ErroFiscal('Inutilização sem protocolo de confirmação.')
            r.status='autorizada'
        return r


def descompactar(valor):
    try:
        dados=base64.b64decode(valor,validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(dados)) as arquivo:
            xml=arquivo.read(5*1024*1024+1)
        if len(xml)>5*1024*1024:raise ValueError
        return xml.decode('utf-8')
    except (ValueError,OSError,UnicodeError):
        raise ErroFiscal('XML comprimido inválido na resposta NFS-e.') from None


class NfseNacionalDireta:
    def base(self, config, doc):
        custom=config.endpoints.get(doc.ambiente,{}).get('nfse',{}).get('emitir')
        return (custom.rstrip('/').removesuffix('/nfse') if custom else
                'https://sefin.'+('producaorestrita.' if doc.ambiente=='homologacao' else '')+'nfse.gov.br/SefinNacional')

    def interpretar(self, resposta, doc):
        try: dados=json.loads(resposta)
        except (ValueError,TypeError):raise ErroFiscal('Resposta NFS-e inválida.') from None
        if dados.get('nfseXmlGZipB64'):
            xml=descompactar(dados['nfseXmlGZipB64']); raiz=xml_seguro(xml)
            inf=raiz.find('.//{*}infNFSe'); chave=(inf.get('Id','').removeprefix('NFS') if inf is not None else '')
            dps=raiz.find('.//{*}infDPS')
            if not chave or dps is None or not dps.get('Id')==doc.identificador_dps:
                raise ErroFiscal('A NFS-e retornada não corresponde à DPS solicitada.')
            return Resultado('autorizada', '100', 'NFS-e autorizada', texto(raiz,'nNFSe'), chave=chave,xml=xml,resposta=resposta)
        erros=dados.get('erros') or []
        if erros:
            erro=erros[0]
            return Resultado('rejeitada',str(erro.get('Codigo','')),str(erro.get('Descricao',''))[:500],resposta=resposta)
        if dados.get('chaveAcesso'):
            return Resultado('pendente',chave=dados['chaveAcesso'],resposta=resposta)
        raise ErroFiscal('Resposta NFS-e sem confirmação fiscal. Consulte a DPS antes de retransmitir.')

    def emitir(self, config, doc):
        dados=json.dumps({'dpsXmlGZipB64':base64.b64encode(gzip.compress(doc.xml_assinado.encode())).decode()}).encode()
        return self.interpretar(requisitar(config,doc.ambiente,self.base(config,doc)+'/nfse',dados),doc)

    def consultar(self, config, doc):
        base=self.base(config,doc)
        if not doc.chave_acesso:
            r=self.interpretar(requisitar(config,doc.ambiente,base+'/dps/'+doc.identificador_dps),doc)
            if not r.chave:return r
            chave=r.chave
        else:chave=doc.chave_acesso
        return self.interpretar(requisitar(config,doc.ambiente,base+'/nfse/'+chave),doc)

    def cancelar(self, config, doc, evento):
        raiz=etree.Element(f'{{{NFSE}}}pedRegEvento',nsmap={None:NFSE},versao='1.01')
        inf=el(raiz,'infPedReg',Id='PRE'+doc.chave_acesso+'101101')
        campos(inf, {'tpAmb':'2' if doc.ambiente=='homologacao' else '1','verAplic':'REGISTER-fiscal-1',
            'dhEvento':timezone.localtime(evento.criado_em).isoformat(timespec='seconds'),'CNPJAutor':doc.snapshot['empresa']['cnpj'],
            'chNFSe':doc.chave_acesso})
        campos(el(inf,'e101101'), {'xDesc':'Cancelamento de NFS-e','cMotivo':'1','xMotivo':evento.justificativa})
        assinatura_xml(raiz,'infPedReg',config,sha256=True);validar_schema(raiz,'pedRegEvento_v1.01.xsd','nfse')
        evento.xml=etree.tostring(raiz,encoding='unicode');evento.save(update_fields=['xml'])
        dados=json.dumps({'pedidoRegistroEventoXmlGZipB64':base64.b64encode(gzip.compress(evento.xml.encode())).decode()}).encode()
        resposta=requisitar(config,doc.ambiente,self.base(config,doc)+'/nfse/'+doc.chave_acesso+'/eventos',dados)
        try:r=json.loads(resposta)
        except ValueError:raise ErroFiscal('Resposta de evento NFS-e inválida.') from None
        if r.get('eventoXmlGZipB64'):
            xml=descompactar(r['eventoXmlGZipB64']);registro=xml_seguro(xml)
            if texto(registro,'chNFSe')!=doc.chave_acesso or not registro.xpath('.//*[local-name()="e101101"]'):
                raise ErroFiscal('O evento NFS-e não confirma o cancelamento da nota solicitada.')
            return Resultado('cancelada','101101','Cancelamento registrado',xml=xml,resposta=resposta)
        return Resultado('rejeitada',mensagem='Cancelamento NFS-e não confirmado.',resposta=resposta)


def provedor(doc):
    if doc.modelo=='nfse':
        from django.conf import settings
        from django.utils.module_loading import import_string
        adaptador=getattr(settings,'FISCAL_NFSE_ADAPTER','')
        return import_string(adaptador)() if adaptador else NfseNacionalDireta()
    return SefazDireta()
