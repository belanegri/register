import re
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from .api import ErroIntegracao


@sensitive_variables()
def cifra():
    try:
        return Fernet(settings.MERCADOLIVRE_TOKEN_KEY.encode())
    except (ValueError, TypeError):
        raise ErroIntegracao("Configure uma MERCADOLIVRE_TOKEN_KEY válida nesta instalação.") from None


@sensitive_variables()
def cifrar(valor):
    return cifra().encrypt(valor.encode()).decode()


@sensitive_variables()
def decifrar(valor):
    try:
        return cifra().decrypt(valor.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise ErroIntegracao("Não foi possível ler os tokens. Confira a chave desta loja ou reconecte a conta.") from None


def validar_configuracao():
    if not settings.MERCADOLIVRE_ENABLED:
        raise ErroIntegracao("Integração desabilitada nesta loja.")
    if not (settings.MERCADOLIVRE_CLIENT_ID.isdigit() and settings.MERCADOLIVRE_CLIENT_SECRET
            and settings.MERCADOLIVRE_SELLER_ID.isdigit() and settings.MERCADOLIVRE_INSTALLATION_ID):
        raise ErroIntegracao("Configure as credenciais, o ID do vendedor e o identificador exclusivo desta loja no Railway.")
    url = urlsplit(settings.MERCADOLIVRE_REDIRECT_URI)
    if (url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment
            or url.path != "/mercado-livre/oauth/callback/" or url.hostname not in settings.ALLOWED_HOSTS):
        raise ErroIntegracao("Configure a URL HTTPS de retorno com o domínio desta loja e o caminho /mercado-livre/oauth/callback/.")
    cifra()


def validar_conexao(conexao):
    validar_configuracao()
    if conexao.escopos:
        validar_escopos(conexao.escopos)
    if (not conexao.conectada or conexao.instalacao != settings.MERCADOLIVRE_INSTALLATION_ID
            or conexao.cliente_id != settings.MERCADOLIVRE_CLIENT_ID
            or conexao.vendedor_id != settings.MERCADOLIVRE_SELLER_ID):
        raise ErroIntegracao("Reconecte a conta autorizada para esta loja.")


def validar_escopos(valor):
    if not isinstance(valor, str) or len(valor) > 4096:
        raise ErroIntegracao("A autorização retornou escopos inválidos.")
    escopos = set(valor.split())
    if not {"read", "offline_access"}.issubset(escopos):
        raise ErroIntegracao("A autorização não incluiu leitura e acesso offline. Confira o fluxo Refresh Token no Developers e reconecte.")
    adicionais = escopos - {"read", "offline_access"}
    # A API também devolve permissões funcionais em URNs. Não aceitar outros
    # produtos (como urn:mp) nem namespaces arbitrários nesta integração.
    if any(e != "write" and not re.fullmatch(r"urn:(?:ml|global):[a-zA-Z0-9._:/-]{1,180}", e) for e in adicionais):
        raise ErroIntegracao("A autorização retornou escopos de outro produto ou não previstos para esta integração.")
    if adicionais and not settings.MERCADOLIVRE_PROVIDER_SCOPE_COMPAT:
        raise ErroIntegracao("O Mercado Livre retornou escopos funcionais ou globais. A compatibilidade exige autorização específica nesta loja; nenhuma credencial foi salva.")
    return escopos
