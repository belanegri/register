"""Preparação, validação e confirmação explícita de uma única peça."""
import hashlib
import json
import re
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from core.auditoria import registrar
from estoque.models import Peca
from .api import ErroIntegracao
from .models import Anuncio, Conexao, Publicacao
from .publicacao_api import ClientePublicacao, Rejeitada
from .seguranca import validar_conexao
from .servicos import token_atual, extrair_anuncio


def autorizar_publicacao(usuario):
    if not (settings.MERCADOLIVRE_ENABLED and settings.MERCADOLIVRE_PUBLISH_ENABLED):
        raise ErroIntegracao("Publicação manual ainda não habilitada nesta loja.")
    if not usuario.has_perms(("mercadolivre.publicar_peca", "estoque.view_peca", "estoque.change_peca")):
        raise ErroIntegracao("Seu usuário não possui permissão para publicar peças.")


def assinatura(peca):
    valores = [peca.pk, peca.atualizado_em.isoformat(), peca.status, peca.quantidade,
               format(Decimal(peca.preco_venda), ".2f"), list(peca.fotos.values_list("pk", "imagem", "atualizado_em"))]
    return hashlib.sha256(json.dumps(valores, default=str).encode()).hexdigest()


def validar_peca(peca):
    if peca.status != Peca.Status.DISPONIVEL or peca.quantidade < 1:
        raise ErroIntegracao("Somente peças disponíveis com estoque podem ser anunciadas.")
    if peca.anuncios_mercadolivre.exclude(status="closed").exists():
        raise ErroIntegracao("Esta peça já possui anúncio vinculado. Gerencie o anúncio existente no Mercado Livre.")


@sensitive_variables()
def acesso_api(usuario):
    autorizar_publicacao(usuario)
    pk, _, token = token_atual()
    conexao = Conexao.objects.get(pk=pk)
    validar_conexao(conexao)
    return conexao, token, ClientePublicacao()


def metadados(usuario, categoria):
    if not re.fullmatch(r"MLB[0-9]{1,20}", categoria):
        raise ErroIntegracao("Escolha uma categoria válida do Mercado Livre.")
    conexao, token, api = acesso_api(usuario)
    categoria_obj = api.enviar("GET", f"/categories/{categoria}", token)
    if categoria_obj.get("id") != categoria or not categoria_obj.get("settings", {}).get("listing_allowed"):
        raise ErroIntegracao("Escolha uma categoria final que permita anúncios.")
    atributos = api.enviar("GET", f"/categories/{categoria}/attributes", token)
    tipos = api.enviar("GET", f"/users/{conexao.vendedor_id}/available_listing_types", token, category_id=categoria)
    return categoria_obj, atributos, tipos.get("available", [])


def fotos_payload(peca, ids):
    fotos = list(peca.fotos.filter(pk__in=ids))
    if not fotos or len(fotos) != len(ids):
        raise ErroIntegracao("Selecione fotos cadastradas nesta peça.")
    saida = []
    for foto in fotos:
        # URLs temporárias são geradas só para a requisição, nunca persistidas no rascunho.
        url = foto.imagem.url
        if not url.startswith("https://"):
            raise ErroIntegracao("As fotos precisam estar disponíveis por HTTPS para o Mercado Livre.")
        saida.append({"source": url})
    return saida


@sensitive_variables()
def preparar(usuario, peca, form):
    conexao, token, api = acesso_api(usuario)
    validar_peca(peca)
    marca = assinatura(peca)
    perfil = api.enviar("GET", "/users/me", token)
    if str(perfil.get("id")) != conexao.vendedor_id:
        raise ErroIntegracao("A conta autenticada não pertence a esta loja.")
    dados = form.cleaned_data
    resumo = {"categoria": form.categoria["name"], "atributos": []}
    for attr, chave in form.atributos:
        valor = dados.get(chave)
        if valor:
            nomes = dict(getattr(form.fields[chave], "choices", []))
            resumo["atributos"].append({"nome": attr["name"], "valor": nomes.get(valor, valor)})
    payload = {"category_id": form.categoria["id"], "price": float(dados["preco"]),
        "currency_id": "BRL", "available_quantity": dados["quantidade"], "buying_mode": "buy_it_now",
        "listing_type_id": dados["tipo"], "condition": dados["condicao"],
        "seller_custom_field": peca.codigo,
        "attributes": form.atributos_payload(),
        "shipping": {"mode": dados["envio"], "local_pick_up": dados["retirada"], "free_shipping": dados["frete_gratis"]}}
    payload["family_name" if "user_product_seller" in perfil.get("tags", []) else "title"] = dados["titulo"]
    fotos = [f.pk for f in dados["fotos"]]
    enviado = {**payload, "pictures": fotos_payload(peca, fotos)}
    api.enviar("POST", "/items/validate", token, enviado)
    with transaction.atomic():
        peca = Peca.objects.select_for_update().get(pk=peca.pk)
        validar_peca(peca)
        if assinatura(peca) != marca:
            raise ErroIntegracao("A peça mudou durante a preparação. Revise os dados novamente.")
        anterior = Publicacao.objects.filter(peca=peca).first()
        if anterior and anterior.estado not in ("revisao", "rejeitada"):
            raise ErroIntegracao("Já existe uma tentativa enviada. Confira o resultado antes de qualquer novo anúncio.")
        if anterior:
            anterior.delete()
        pub = Publicacao.objects.create(peca=peca, conexao=conexao, usuario=usuario, payload=payload, resumo=resumo,
            descricao=dados["descricao"], fotos=fotos, assinatura=marca)
        registrar(usuario, "mercadolivre.publicacao_preparada", peca.codigo, tentativa=str(pub.pk))
    return pub


@sensitive_variables()
def confirmar(usuario, pk):
    conexao, token, api = acesso_api(usuario)  # refresh deve ser confirmado antes da transação de envio
    with transaction.atomic():
        # Mesma ordem de locks em preparação e confirmação: peça antes da tentativa.
        referencia = Publicacao.objects.get(pk=pk)
        peca = Peca.objects.select_for_update().get(pk=referencia.peca_id)
        pub = Publicacao.objects.select_for_update().get(pk=pk)
        if pub.usuario_id != usuario.pk or pub.conexao_id != conexao.pk or pub.estado != "revisao":
            raise ErroIntegracao("Esta tentativa não pode ser enviada novamente.")
        validar_peca(peca)
        if pub.criado_em < timezone.now() - timedelta(minutes=15) or assinatura(peca) != pub.assinatura:
            raise ErroIntegracao("Revisão expirada ou peça alterada. Prepare o anúncio novamente.")
        if pub.payload["available_quantity"] > peca.quantidade:
            raise ErroIntegracao("Quantidade superior ao estoque disponível.")
        dados = {**pub.payload, "pictures": fotos_payload(peca, pub.fotos)}
        pub.estado = "enviando"
        pub.save(update_fields=["estado", "atualizado_em"])
        registrar(usuario, "mercadolivre.publicacao_confirmada", peca.codigo, tentativa=str(pub.pk))
    # Commit antes do POST: interrupção ou resposta perdida bloqueia reenvio e duplicação.
    try:
        api.enviar("POST", "/items/validate", token, dados)
    except ErroIntegracao:
        Publicacao.objects.filter(pk=pk).update(estado="rejeitada")
        raise
    try:
        validar_conexao(Conexao.objects.get(pk=conexao.pk))
        resposta = api.enviar("POST", "/items", token, dados)
    except Rejeitada as erro:
        Publicacao.objects.filter(pk=pk).update(estado="rejeitada", aviso=str(erro)[:500])
        raise
    except ErroIntegracao as erro:
        Publicacao.objects.filter(pk=pk).update(estado="incerta", aviso=str(erro)[:500])
        raise
    item_id = resposta.get("id", "") if isinstance(resposta, dict) else ""
    if not isinstance(item_id, str) or not re.fullmatch(r"MLB[0-9]+", item_id) or str(resposta.get("seller_id")) != conexao.vendedor_id:
        Publicacao.objects.filter(pk=pk).update(estado="incerta", aviso="Confira a criação no Mercado Livre e importe os anúncios. Não repita o envio.")
        raise ErroIntegracao("Resultado inconclusivo. Confira os anúncios na conta da loja; o reenvio foi bloqueado.")
    # Registrar o ID antes de qualquer operação complementar.
    Publicacao.objects.filter(pk=pk).update(estado="publicada", item_id=item_id, aviso="")
    try:
        snapshot = extrair_anuncio(resposta, conexao.vendedor_id)
        snapshot["peca"] = peca
        Anuncio.objects.update_or_create(conexao=conexao, item_id=item_id, defaults=snapshot)
    except (ErroIntegracao, KeyError, TypeError, ValueError):
        Publicacao.objects.filter(pk=pk).update(aviso="Anúncio criado. Importe os anúncios para completar o vínculo local.")
    try:
        api.enviar("POST", f"/items/{item_id}/description", token, {"plain_text": pub.descricao})
    except ErroIntegracao:
        Publicacao.objects.filter(pk=pk).update(aviso="Anúncio criado, mas a descrição não foi confirmada. Confira e complete a descrição diretamente no Mercado Livre.")
    registrar(usuario, "mercadolivre.publicada", item_id, peca_id=peca.pk, tentativa=str(pk))
    return Publicacao.objects.get(pk=pk)
