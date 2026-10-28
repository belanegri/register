"""Homologação SEFAZ-SP: MOC 7.0 seção 5.5, status 4.00, SOAP 1.2/mTLS.

Fontes oficiais (consulta em 05/10/2026):
https://portal.fazenda.sp.gov.br/servicos/nfe/Paginas/URL-WEBSERVICES.aspx
https://portal.fazenda.sp.gov.br/servicos/nfce/Paginas/WebServices.aspx
https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=LrBx7WT9PuA%3D
Consulta de status não exige assinatura XML, somente autenticação mTLS A1.
"""
from dataclasses import dataclass
import re
from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from lxml import etree
from .seguranca import ErroFiscal, ErroCertificadoFiscal, material_a1, xml_seguro
from .xml import NFE, campos

ENDPOINTS = {
    '55': {
        'emitir': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx',
        'consultar': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx',
        'recibo': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx',
        'cancelar': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx',
        'inutilizar': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeinutilizacao4.asmx',
        'status': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx',
    },
    '65': {
        'emitir': 'https://homologacao.nfce.fazenda.sp.gov.br/ws/NFeAutorizacao4.asmx',
        'consultar': 'https://homologacao.nfce.fazenda.sp.gov.br/ws/NFeConsultaProtocolo4.asmx',
        'recibo': 'https://homologacao.nfce.fazenda.sp.gov.br/ws/NFeRetAutorizacao4.asmx',
        'cancelar': 'https://homologacao.nfce.fazenda.sp.gov.br/ws/NFeRecepcaoEvento4.asmx',
        'inutilizar': 'https://homologacao.nfce.fazenda.sp.gov.br/ws/NFeInutilizacao4.asmx',
        'status': 'https://homologacao.nfce.fazenda.sp.gov.br/ws/NFeStatusServico4.asmx',
    },
}


ENDPOINTS_PRODUCAO_NFE = {nome:url.replace('homologacao.nfe.','nfe.') for nome,url in ENDPOINTS['55'].items()}


def endpoint(config, modelo, operacao, ambiente):
    if config.uf != 'SP' or modelo not in ENDPOINTS or operacao not in ENDPOINTS[modelo]:
        raise ErroFiscal('Configure UF SP e um serviço válido de NF-e/NFC-e.')
    if ambiente == 'homologacao':
        oficial=ENDPOINTS[modelo][operacao]
    elif ambiente == 'producao' and modelo == '55':
        if operacao != 'status' and not (settings.FISCAL_ENABLED and settings.FISCAL_ALLOW_PRODUCTION and config.ativa and config.homologacao_validada and config.producao_validada):
            raise ErroFiscal('Produção bloqueada. Conclua a homologação e a liberação desta instalação.')
        oficial=ENDPOINTS_PRODUCAO_NFE[operacao]
    else:
        raise ErroFiscal('Produção disponível somente para NF-e (55) da SEFAZ-SP.')
    personalizado = config.endpoints.get(ambiente, {}).get(modelo, {}).get(operacao)
    if personalizado and personalizado != oficial:
        raise ErroFiscal('Use exclusivamente o endpoint oficial da SEFAZ-SP correspondente ao ambiente.')
    return oficial


@dataclass(frozen=True)
class ResultadoConexao:
    status: str
    mensagem: str
    codigo: str = ''


def consultar_status(config, modelo):
    from .provedores import requisitar
    url = endpoint(config, modelo, 'status', config.ambiente)
    soap_ns = 'http://www.w3.org/2003/05/soap-envelope'
    servico_ns = NFE + '/wsdl/NFeStatusServico4'
    envelope = etree.Element(f'{{{soap_ns}}}Envelope', nsmap={'soap': soap_ns})
    body = etree.SubElement(envelope, f'{{{soap_ns}}}Body')
    mensagem = etree.SubElement(body, f'{{{servico_ns}}}nfeDadosMsg')
    consulta = etree.SubElement(mensagem, f'{{{NFE}}}consStatServ', nsmap={None: NFE}, versao='4.00')
    campos(consulta, {'tpAmb': '2' if config.ambiente=='homologacao' else '1', 'cUF': '35', 'xServ': 'STATUS'})
    resposta = requisitar(config, config.ambiente, url,
        etree.tostring(envelope, encoding='utf-8', xml_declaration=True),
        f'application/soap+xml; charset=utf-8; action="{servico_ns}/nfeStatusServicoNF"')
    raiz = xml_seguro(resposta)
    if raiz.xpath('.//*[local-name()="Fault"]'):
        return ResultadoConexao('erro_sefaz', 'Erro retornado pela SEFAZ: falha SOAP no serviço de status.')
    retornos = raiz.xpath('descendant-or-self::n:retConsStatServ', namespaces={'n': NFE})
    if len(retornos) != 1:
        raise ErroFiscal('Resposta SEFAZ sem confirmação válida do serviço de status.')
    retorno = retornos[0]
    campo = lambda nome: retorno.findtext(f'{{{NFE}}}{nome}', '')
    codigo = campo('cStat')
    if (retorno.get('versao') != '4.00' or campo('tpAmb') != ('2' if config.ambiente=='homologacao' else '1') or campo('cUF') != '35'
            or not re.fullmatch(r'\d{3}', codigo) or not campo('xMotivo')
            or not campo('verAplic') or not campo('dhRecbto')):
        raise ErroFiscal('Resposta SEFAZ inválida ou incompatível com o ambiente selecionado em SP.')
    if codigo == '107':
        return ResultadoConexao('conectado', f'Conectado — SEFAZ-SP {config.get_ambiente_display()}: serviço em operação (107).', codigo)
    # Não ecoar conteúdo livre da resposta, que pode incluir dados sensíveis.
    conhecidos = {'108': 'serviço paralisado momentaneamente', '109': 'serviço paralisado sem previsão',
                  '252': 'ambiente divergente', '289': 'UF divergente', '280': 'certificado inválido',
                  '281': 'certificado vencido', '282': 'certificado sem CNPJ', '283': 'cadeia do certificado inválida',
                  '284': 'certificado revogado', '285': 'certificado difere de ICP-Brasil',
                  '286': 'consulta de revogação indisponível'}
    status = 'certificado_invalido' if codigo in ('280','281','282','283','284','285') else 'erro_sefaz'
    return ResultadoConexao(status, f'Erro retornado pela SEFAZ ({codigo}): '+conhecidos.get(codigo, 'consulta de status rejeitada'), codigo)


@sensitive_variables()
def testar_conexao(config, modelo):
    if config is None:
        return ResultadoConexao('configuracao_ausente', 'Configuração ausente: salve a configuração fiscal de homologação.')
    if not settings.FISCAL_SECRET_KEY:
        return ResultadoConexao('configuracao_ausente', 'Configuração ausente: configure a chave de criptografia fiscal da instalação.')
    try:
        endpoint(config, modelo, 'status', config.ambiente)
    except ErroFiscal as erro:
        return ResultadoConexao('configuracao_ausente', str(erro))
    if not config.certificado_criptografado or not config.senha_a1_criptografada:
        return ResultadoConexao('configuracao_ausente', 'Configuração ausente: cadastre o certificado A1 e sua senha na tela fiscal.')
    try:
        material_a1(config)
    except ErroFiscal:
        return ResultadoConexao('certificado_invalido', 'Certificado inválido: confira validade, arquivo A1, senha e chave de criptografia da instalação.')
    try:
        return consultar_status(config, modelo)
    except ErroCertificadoFiscal:
        return ResultadoConexao('certificado_invalido', 'Certificado inválido ou recusado na autenticação TLS da SEFAZ.')
    except Exception:
        return ResultadoConexao('erro_sefaz', 'Erro de comunicação ou resposta da SEFAZ. Confira a conexão e tente novamente mais tarde.')
