"""Transporte de publicação separado do cliente de importação, sem PUT/DELETE."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from .api import ErroIntegracao, SemRedirect


class Rejeitada(ErroIntegracao):
    pass


class ClientePublicacao:
    LEITURAS = re.compile(r"/(?:users/me|categories/MLB[0-9]+(?:/attributes)?|sites/MLB/domain_discovery/search|users/[0-9]+/available_listing_types)\Z")
    ESCRITAS = re.compile(r"/items(?:/validate|/MLB[0-9]+/description)?\Z")

    @sensitive_variables()
    def enviar(self, metodo, caminho, token, dados=None, **parametros):
        if not settings.MERCADOLIVRE_ENABLED or not settings.MERCADOLIVRE_PUBLISH_ENABLED:
            raise ErroIntegracao("Publicação manual ainda não habilitada nesta loja.")
        if not ((metodo == "GET" and self.LEITURAS.fullmatch(caminho)) or
                (metodo == "POST" and self.ESCRITAS.fullmatch(caminho))):
            raise ErroIntegracao("Operação não autorizada no fluxo de publicação manual.")
        url = "https://api.mercadolibre.com" + caminho
        if parametros:
            url += "?" + urlencode(parametros)
        body = json.dumps(dados, allow_nan=False).encode() if dados is not None else None
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json"}
        try:
            with build_opener(SemRedirect()).open(Request(url, data=body, headers=headers, method=metodo), timeout=25) as resposta:
                raw = resposta.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ErroIntegracao("Resposta inválida. Confira o anúncio no Mercado Livre antes de tentar novamente.")
                return json.loads(raw) if raw else {}
        except HTTPError as erro:
            # Somente rejeições explícitas permitem nova preparação. Timeout/5xx/redirect
            # podem ocorrer após criação e nunca autorizam repetir POST /items.
            if erro.code in (400, 401, 403, 422, 429):
                codigos = []
                try:
                    obj = json.loads(erro.read(65536))
                    codigos = [c.get("code", "") for c in obj.get("cause", []) if isinstance(c, dict)]
                except (ValueError, TypeError, AttributeError):
                    pass
                codigos = [c for c in codigos if isinstance(c, str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", c)][:8]
                orientacao = {401: "Reconecte a conta.", 403: "Confira a permissão de publicação da aplicação e reconecte.",
                             429: "Aguarde antes de tentar novamente."}.get(erro.code, "Revise categoria, características, fotos, envio e preço.")
                raise Rejeitada("Mercado Livre recusou a solicitação. " + orientacao + (" Códigos: " + ", ".join(codigos) if codigos else "")) from None
            raise ErroIntegracao("Resposta inconclusiva. Confira o anúncio no Mercado Livre antes de qualquer novo envio.") from None
        except (URLError, OSError, TimeoutError, ValueError):
            raise ErroIntegracao("Falha de comunicação. Confira o anúncio no Mercado Livre antes de qualquer novo envio.") from None
