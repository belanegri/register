import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from .api import Cliente, ErroIntegracao
from .models import Anuncio, Conexao
from .seguranca import cifrar, decifrar, validar_conexao, validar_configuracao


@sensitive_variables()
def formulario_oauth(**campos):
    return {"client_id": settings.MERCADOLIVRE_CLIENT_ID,
            "client_secret": settings.MERCADOLIVRE_CLIENT_SECRET, **campos}


@sensitive_variables()
def salvar_tokens(conexao, dados):
    try:
        if str(dados["user_id"]) != settings.MERCADOLIVRE_SELLER_ID:
            raise ErroIntegracao("A conta autorizada não corresponde ao vendedor configurado para esta loja.")
        scopes = set(dados["scope"].split())
        if not {"read", "offline_access"}.issubset(scopes) or "write" in scopes:
            raise ErroIntegracao("Autorize somente leitura e acesso offline na aplicação do Mercado Livre; remova a permissão de escrita e reconecte.")
        segundos = int(dados["expires_in"])
        if segundos <= 0 or not dados["access_token"] or not dados["refresh_token"]:
            raise ValueError
        conexao.access_token_cifrado = cifrar(dados["access_token"])
        conexao.refresh_token_cifrado = cifrar(dados["refresh_token"])
        conexao.expira_em = timezone.now() + timedelta(seconds=segundos)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ErroIntegracao("Mercado Livre retornou credenciais incompletas. Reconecte a conta.") from None


@sensitive_variables()
def conectar(codigo, verifier):
    validar_configuracao()
    cliente = Cliente()
    dados = cliente.token(formulario_oauth(grant_type="authorization_code", code=codigo,
                           redirect_uri=settings.MERCADOLIVRE_REDIRECT_URI, code_verifier=verifier))
    # Validar identidade e cifra antes de persistir qualquer credencial.
    nova = Conexao()
    salvar_tokens(nova, dados)
    perfil = cliente.consultar("/users/me", dados["access_token"])
    if not isinstance(perfil, dict) or str(perfil.get("id")) != settings.MERCADOLIVRE_SELLER_ID:
        raise ErroIntegracao("A conta retornada não corresponde ao vendedor desta loja.")
    with transaction.atomic():
        conexao, _ = Conexao.objects.get_or_create(unica=True)
        conexao = Conexao.objects.select_for_update().get(pk=conexao.pk)
        if conexao.vendedor_id and conexao.vendedor_id != settings.MERCADOLIVRE_SELLER_ID:
            raise ErroIntegracao("Esta instalação já possui histórico de outro vendedor. Não é permitido misturar contas.")
        conexao.instalacao = settings.MERCADOLIVRE_INSTALLATION_ID
        conexao.cliente_id = settings.MERCADOLIVRE_CLIENT_ID
        conexao.vendedor_id = settings.MERCADOLIVRE_SELLER_ID
        conexao.apelido = str(perfil.get("nickname", ""))[:200]
        conexao.access_token_cifrado = nova.access_token_cifrado
        conexao.refresh_token_cifrado = nova.refresh_token_cifrado
        conexao.expira_em = nova.expira_em
        conexao.conectada = True
        conexao.cursor = ""
        conexao.cursor_expira_em = None
        conexao.importacao_concluida = False
        conexao.save()
    return conexao


@sensitive_variables()
def token_atual():
    # A transação termina ANTES da importação: falha em GET não perde o refresh
    # token rotacionado. O lock impede renovações concorrentes com o mesmo token.
    with transaction.atomic():
        conexao = Conexao.objects.select_for_update().filter(unica=True).first()
        if not conexao:
            raise ErroIntegracao("Conecte a conta antes de importar.")
        validar_conexao(conexao)
        if not conexao.expira_em or conexao.expira_em <= timezone.now() + timedelta(seconds=60):
            dados = Cliente().token(formulario_oauth(grant_type="refresh_token", refresh_token=decifrar(conexao.refresh_token_cifrado)))
            salvar_tokens(conexao, dados)
            conexao.save()
        return conexao.pk, conexao.access_token_cifrado, decifrar(conexao.access_token_cifrado)


def extrair_anuncio(item, vendedor_id):
    try:
        if str(item["seller_id"]) != vendedor_id or not re.fullmatch(r"MLB[0-9]+", item["id"]):
            raise ValueError
        preco = Decimal(str(item["price"]))
        if not preco.is_finite() or preco < 0 or preco >= Decimal("100000000000000"):
            raise ValueError
        quantidade, vendidos = int(item["available_quantity"]), int(item.get("sold_quantity", 0))
        if min(quantidade, vendidos) < 0:
            raise ValueError
        variacoes = [{"id": str(v["id"]), "quantidade": int(v.get("available_quantity", 0))}
                    for v in item.get("variations", [])]
        return {"titulo": str(item["title"])[:300], "status": str(item["status"])[:40],
                "preco": preco, "moeda": str(item["currency_id"])[:10],
                "quantidade": quantidade, "vendidos": vendidos,
                "sku": str(item.get("seller_custom_field") or "")[:200], "variacoes": variacoes}
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise ErroIntegracao("Anúncio inválido ou de outra conta. O lote não foi importado.") from None


@sensitive_variables()
def importar_lote(*, reiniciar=False):
    pk, token_cifrado, token = token_atual()
    with transaction.atomic():
        conexao = Conexao.objects.select_for_update().get(pk=pk)
        validar_conexao(conexao)
        if conexao.access_token_cifrado != token_cifrado:
            raise ErroIntegracao("A conexão mudou. Tente a importação novamente.")
        if conexao.importacao_concluida and not reiniciar:
            return 0, True
        parametros = {"search_type": "scan", "limit": 20}
        if not reiniciar and conexao.cursor:
            if not conexao.cursor_expira_em or conexao.cursor_expira_em <= timezone.now():
                raise ErroIntegracao("A busca expirou. Clique em Reiniciar importação; os vínculos serão preservados.")
            parametros["scroll_id"] = conexao.cursor
        cliente = Cliente()
        busca = cliente.consultar(f"/users/{conexao.vendedor_id}/items/search", token, **parametros)
        if not isinstance(busca, dict) or not isinstance(busca.get("results"), list):
            raise ErroIntegracao("Mercado Livre retornou uma busca inválida.")
        ids = busca["results"]
        if len(ids) > 20 or any(not isinstance(i, str) or not re.fullmatch(r"MLB[0-9]+", i) for i in ids) or len(set(ids)) != len(ids):
            raise ErroIntegracao("Mercado Livre retornou identificadores inválidos.")
        anuncios = []
        if ids:
            resultado = cliente.consultar("/items/bulk", token, ids=",".join(ids))
            if not isinstance(resultado, list) or len(resultado) != len(ids):
                raise ErroIntegracao("Consulta incompleta. Nenhum anúncio deste lote foi atualizado.")
            encontrados = set()
            for registro in resultado:
                if not isinstance(registro, dict) or registro.get("status_code") != 200 or not isinstance(registro.get("body"), dict):
                    raise ErroIntegracao("Um anúncio não pôde ser consultado. Reinicie a importação para tentar novamente.")
                item = registro["body"]
                item_id = item.get("id")
                if item_id not in ids or item_id in encontrados:
                    raise ErroIntegracao("Resposta de anúncios inconsistente.")
                encontrados.add(item_id)
                anuncios.append((item_id, extrair_anuncio(item, conexao.vendedor_id)))
        cursor = busca.get("scroll_id", parametros.get("scroll_id", "")) or ""
        if ids and not isinstance(cursor, str):
            raise ErroIntegracao("Cursor de importação inválido.")
        for item_id, campos in anuncios:
            # Não tocar peca, estoque, preços locais ou postada_online.
            Anuncio.objects.update_or_create(conexao=conexao, item_id=item_id, defaults=campos)
        conexao.cursor = cursor if ids else ""
        if not conexao.cursor:
            conexao.cursor_expira_em = None
        elif "scroll_id" not in parametros:
            conexao.cursor_expira_em = timezone.now() + timedelta(minutes=4)
        conexao.importacao_concluida = not ids or not cursor
        conexao.ultima_importacao = timezone.now()
        conexao.save()
        return len(anuncios), conexao.importacao_concluida
