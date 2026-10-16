"""Transporte fechado: GETs conhecidos e POST apenas em /oauth/token."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.views.decorators.debug import sensitive_variables


class ErroIntegracao(Exception):
    pass


class SemRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Cliente:
    BASE = "https://api.mercadolibre.com"
    LEITURAS = re.compile(r"/(?:users/me|users/[0-9]+/items/search|items/bulk)\Z")

    @sensitive_variables()
    def _enviar(self, metodo, caminho, *, token="", parametros=None, formulario=None):
        if not ((metodo == "GET" and self.LEITURAS.fullmatch(caminho)) or
                (metodo == "POST" and caminho == "/oauth/token")):
            raise ErroIntegracao("Operação bloqueada: integração em modo somente leitura.")
        url = self.BASE + caminho
        if parametros:
            url += "?" + urlencode(parametros)
        headers = {"Accept": "application/json", "User-Agent": "REGISTER-MercadoLivre/1.0"}
        if token:
            headers["Authorization"] = "Bearer " + token
        dados = None
        if formulario is not None:
            dados = urlencode(formulario).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            # Não seguir redirects: jamais encaminhar tokens a outro endereço.
            with build_opener(SemRedirect()).open(Request(url, data=dados, headers=headers, method=metodo), timeout=15) as resposta:
                conteudo = resposta.read(2 * 1024 * 1024 + 1)
                if len(conteudo) > 2 * 1024 * 1024:
                    raise ErroIntegracao("Resposta do Mercado Livre excedeu o limite permitido.")
                return json.loads(conteudo)
        except HTTPError as erro:
            mensagens = {401: "Acesso expirado ou revogado. Reconecte a conta.",
                         403: "Mercado Livre negou acesso. Confira as permissões da aplicação.",
                         429: "Limite de consultas atingido. Aguarde antes de tentar novamente."}
            raise ErroIntegracao(mensagens.get(erro.code, "Mercado Livre não concluiu a consulta. Tente novamente ou reconecte a conta.")) from None
        except (URLError, TimeoutError, OSError, ValueError):
            # Nunca exibir corpo da resposta, URL OAuth, código ou credenciais.
            raise ErroIntegracao("Falha de comunicação com o Mercado Livre. Tente novamente.") from None

    @sensitive_variables()
    def token(self, formulario):
        return self._enviar("POST", "/oauth/token", formulario=formulario)

    @sensitive_variables()
    def consultar(self, caminho, token, **parametros):
        return self._enviar("GET", caminho, token=token, parametros=parametros)
