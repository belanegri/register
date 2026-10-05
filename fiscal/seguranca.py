import base64
import hashlib
import os
import re
import ssl
from contextlib import contextmanager
from datetime import timezone as utc_timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from lxml import etree


class ErroFiscal(Exception):
    """Mensagem sanitizada, apropriada para interface e histórico fiscal."""


def cifrador():
    try:
        return Fernet(settings.FISCAL_SECRET_KEY.encode('ascii'))
    except (ValueError, AttributeError, UnicodeError):
        raise ErroFiscal("Configure FISCAL_SECRET_KEY exclusiva desta instalação.") from None


@sensitive_variables()
def criptografar(valor):
    return cifrador().encrypt(valor if isinstance(valor, bytes) else valor.encode('utf-8'))


@sensitive_variables()
def descriptografar(valor):
    try:
        return cifrador().decrypt(bytes(valor))
    except (InvalidToken, TypeError):
        raise ErroFiscal("Não foi possível abrir o segredo fiscal desta instalação.") from None


@sensitive_variables()
def ler_a1(dados, senha):
    try:
        chave, cert, cadeia = pkcs12.load_key_and_certificates(dados, senha.encode('utf-8'))
    except (ValueError, TypeError):
        raise ErroFiscal("Certificado A1 ou senha inválidos.") from None
    if not cert or not isinstance(chave, rsa.RSAPrivateKey):
        raise ErroFiscal("Envie um certificado A1 RSA com chave privada.")
    if cert.public_key().public_numbers() != chave.public_key().public_numbers():
        raise ErroFiscal("O certificado não corresponde à chave privada.")
    if not cert.not_valid_before_utc <= timezone.now() < cert.not_valid_after_utc:
        raise ErroFiscal("O certificado A1 está vencido ou ainda não é válido.")
    return chave, cert, cadeia or []


@sensitive_variables()
def salvar_a1(config, dados, senha):
    if len(dados) > 1024 * 1024:
        raise ErroFiscal("O certificado A1 deve ter até 1 MB.")
    _, cert, _ = ler_a1(dados, senha)
    config.certificado_criptografado = criptografar(dados)
    config.senha_a1_criptografada = criptografar(senha)
    config.certificado_valido_desde = cert.not_valid_before_utc
    config.certificado_valido_ate = cert.not_valid_after_utc
    config.certificado_fingerprint = cert.fingerprint(hashes.SHA256()).hex()


@sensitive_variables()
def material_a1(config):
    if config.certificado_vencido:
        raise ErroFiscal("Configure um certificado A1 válido antes da transmissão.")
    return ler_a1(descriptografar(config.certificado_criptografado),
                  descriptografar(config.senha_a1_criptografada).decode('utf-8'))


def validar_url(url, ambiente=None):
    partes = urlsplit(url)
    host = (partes.hostname or '').lower()
    permitidos = set(settings.FISCAL_ENDPOINT_HOSTS)
    if (partes.scheme != 'https' or partes.username or partes.password or partes.fragment
            or partes.port not in (None, 443) or not (host.endswith('.gov.br') or host in permitidos)):
        raise ErroFiscal("Use um endereço HTTPS oficial do serviço fiscal.")
    if ambiente == 'homologacao' and not any(s in host for s in ('hom', 'hml', 'teste', 'producaorestrita')):
        raise ErroFiscal("O endereço informado não identifica o ambiente de homologação.")
    return url


def validar_endpoints(endpoints):
    if not isinstance(endpoints, dict):
        raise ValidationError({'endpoints': 'Informe um objeto JSON por ambiente, modelo e operação.'})
    try:
        for ambiente, modelos in endpoints.items():
            if ambiente not in ('homologacao', 'producao') or not isinstance(modelos, dict):
                raise ErroFiscal("Ambiente de endpoint inválido.")
            for modelo, operacoes in modelos.items():
                if modelo not in ('55', '65', 'nfse') or not isinstance(operacoes, dict):
                    raise ErroFiscal("Modelo de endpoint inválido.")
                for operacao, url in operacoes.items():
                    if operacao not in ('emitir', 'consultar', 'recibo', 'cancelar', 'inutilizar', 'qr_code', 'consulta_publica', 'danfse'):
                        raise ErroFiscal("Operação de endpoint inválida.")
                    validar_url(url, ambiente)
    except (ErroFiscal, ValueError, TypeError):
        raise ValidationError({'endpoints': 'Revise os endereços HTTPS oficiais e seus ambientes.'}) from None


def xml_seguro(valor):
    dados = valor.encode('utf-8') if isinstance(valor, str) else valor
    if len(dados) > 5 * 1024 * 1024 or b'<!DOCTYPE' in dados.upper() or b'<!ENTITY' in dados.upper():
        raise ErroFiscal("XML fiscal inválido.")
    try:
        return etree.fromstring(dados, parser=etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
    except etree.XMLSyntaxError:
        raise ErroFiscal("XML fiscal inválido.") from None


def assinatura_xml(raiz, tag, config, sha256=False):
    from cryptography.hazmat.primitives.asymmetric import padding
    alvo = raiz.find(f'.//{{*}}{tag}')
    if alvo is None or not alvo.get('Id'):
        raise ErroFiscal("Identificador do XML fiscal ausente.")
    chave, certificado, _ = material_a1(config)
    ns = 'http://www.w3.org/2000/09/xmldsig#'
    algoritmo = hashes.SHA256() if sha256 else hashes.SHA1()
    canon = lambda el: etree.tostring(el, method='c14n', exclusive=False)
    assinatura = etree.SubElement(raiz, f'{{{ns}}}Signature', nsmap={None: ns})
    info = etree.SubElement(assinatura, f'{{{ns}}}SignedInfo')
    etree.SubElement(info, f'{{{ns}}}CanonicalizationMethod', Algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315')
    etree.SubElement(info, f'{{{ns}}}SignatureMethod', Algorithm=('http://www.w3.org/2001/04/xmldsig-more#rsa-sha256' if sha256 else ns+'rsa-sha1'))
    ref = etree.SubElement(info, f'{{{ns}}}Reference', URI='#'+alvo.get('Id'))
    transforms = etree.SubElement(ref, f'{{{ns}}}Transforms')
    for alg in (ns+'enveloped-signature', 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315'):
        etree.SubElement(transforms, f'{{{ns}}}Transform', Algorithm=alg)
    etree.SubElement(ref, f'{{{ns}}}DigestMethod', Algorithm=('http://www.w3.org/2001/04/xmlenc#sha256' if sha256 else ns+'sha1'))
    digest = hashlib.sha256(canon(alvo)).digest() if sha256 else hashlib.sha1(canon(alvo)).digest()
    etree.SubElement(ref, f'{{{ns}}}DigestValue').text = base64.b64encode(digest).decode()
    etree.SubElement(assinatura, f'{{{ns}}}SignatureValue').text = base64.b64encode(chave.sign(canon(info), padding.PKCS1v15(), algoritmo)).decode()
    ki = etree.SubElement(assinatura, f'{{{ns}}}KeyInfo')
    xd = etree.SubElement(ki, f'{{{ns}}}X509Data')
    etree.SubElement(xd, f'{{{ns}}}X509Certificate').text = base64.b64encode(certificado.public_bytes(serialization.Encoding.DER)).decode()
    return raiz


@contextmanager
@sensitive_variables()
def contexto_tls(config):
    chave, cert, cadeia = material_a1(config)
    senha_temporaria = base64.urlsafe_b64encode(os.urandom(32))
    # A chave privada temporária também é criptografada; nunca PEM aberto no disco.
    with TemporaryDirectory(prefix='register-fiscal-') as pasta:
        cp, kp = Path(pasta)/'cert', Path(pasta)/'key'
        cp.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + b''.join(c.public_bytes(serialization.Encoding.PEM) for c in cadeia))
        kp.write_bytes(chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.BestAvailableEncryption(senha_temporaria)))
        cp.chmod(0o600); kp.chmod(0o600)
        contexto = ssl.create_default_context()
        contexto.minimum_version = ssl.TLSVersion.TLSv1_2
        contexto.load_cert_chain(str(cp), str(kp), password=senha_temporaria.decode())
        yield contexto


def resposta_sanitizada(texto):
    import json
    try:
        dados=json.loads(texto)
        def filtrar(v):
            if isinstance(v,dict):
                return {k:filtrar(item) for k,item in v.items() if not any(s in k.lower() for s in ('cert','senha','password','csc','token','xmlgzip'))}
            if isinstance(v,list):return [filtrar(i) for i in v]
            return v
        texto=json.dumps(filtrar(dados),ensure_ascii=False)
    except (ValueError,TypeError):
        pass
    # Histórico técnico não guarda o certificado público presente na assinatura.
    texto = re.sub(r'<(?:\w+:)?X509Certificate\b[^>]*>.*?</(?:\w+:)?X509Certificate>', '[certificado omitido]', texto, flags=re.S)
    texto = re.sub(r'(?i)(senha|password|csc|token)\s*[=:]\s*[^\s<,]+', r'\1=[omitido]', texto)
    return texto[:100000]
