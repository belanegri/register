import base64
import hashlib
import secrets
from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from core.auditoria import registrar
from estoque.models import Peca
from .api import ErroIntegracao
from .forms import VinculoForm
from .models import Anuncio, Conexao, Publicacao, Selecao, TentativaOAuth
from .seguranca import validar_configuracao
from .servicos import conectar, importar_lote


def acesso(view):
    @wraps(view)
    def habilitada(request, *args, **kwargs):
        if not settings.MERCADOLIVRE_ENABLED:
            return render(request, "mercadolivre/desabilitada.html", status=403)
        response = view(request, *args, **kwargs)
        # Formulários HTTPS precisam preservar a origem para a proteção CSRF.
        # Os redirects OAuth continuam sem referência, pois podem conter códigos.
        response["Referrer-Policy"] = "no-referrer" if view.__name__ in {"callback", "autorizar"} else "same-origin"
        return response
    return login_required(permission_required("mercadolivre.gerenciar_integracao", raise_exception=True)(never_cache(habilitada)))


def identidade_config():
    valores = [settings.MERCADOLIVRE_CLIENT_ID, settings.MERCADOLIVRE_REDIRECT_URI,
               settings.MERCADOLIVRE_INSTALLATION_ID, settings.MERCADOLIVRE_SELLER_ID,
               str(settings.MERCADOLIVRE_PROVIDER_SCOPE_COMPAT)]
    return hashlib.sha256("\n".join(valores).encode()).hexdigest()


@acesso
@require_GET
def painel(request):
    erro_config = ""
    try:
        validar_configuracao()
    except ErroIntegracao as erro:
        erro_config = str(erro)
    q = request.GET.get("q", "").strip()[:200]
    anuncios = Anuncio.objects.select_related("peca")
    if q:
        anuncios = anuncios.filter(Q(item_id__icontains=q) | Q(titulo__icontains=q) | Q(peca__codigo__icontains=q))
    return render(request, "mercadolivre/painel.html", {"conexao": Conexao.objects.first(),
        "publicacao_habilitada": settings.MERCADOLIVRE_PUBLISH_ENABLED,
        "publicacoes": Publicacao.objects.filter(usuario=request.user).select_related("peca").order_by("-atualizado_em")[:10] if settings.MERCADOLIVRE_PUBLISH_ENABLED else [],
        "erro_config": erro_config, "q": q, "pagina": Paginator(anuncios, 20).get_page(request.GET.get("page")),
        "selecoes": Selecao.objects.select_related("peca", "usuario").order_by("-criado_em")[:50]})


@acesso
@require_POST
@sensitive_variables()
def autorizar(request):
    try:
        validar_configuracao()
    except ErroIntegracao as erro:
        messages.error(request, str(erro))
        return redirect("mercadolivre:painel")
    estado, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    TentativaOAuth.objects.filter(expira_em__lt=timezone.now()).delete()
    TentativaOAuth.objects.create(estado_hash=hashlib.sha256(estado.encode()).hexdigest(),
                                  usuario=request.user, expira_em=timezone.now() + timedelta(minutes=10))
    request.session["ml_oauth"] = {"estado": estado, "verifier": verifier, "config": identidade_config()}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return redirect("https://auth.mercadolivre.com.br/authorization?" + urlencode({
        "response_type": "code", "client_id": settings.MERCADOLIVRE_CLIENT_ID,
        "redirect_uri": settings.MERCADOLIVRE_REDIRECT_URI, "state": estado,
        "scope": "read write offline_access" if settings.MERCADOLIVRE_PUBLISH_ENABLED else "read offline_access",
        "code_challenge": challenge, "code_challenge_method": "S256"}))


@acesso
@require_GET
@sensitive_variables()
def callback(request):
    tentativa = request.session.pop("ml_oauth", None)
    estado = request.GET.get("state", "")
    if (not tentativa or not estado or not secrets.compare_digest(estado.encode(), tentativa["estado"].encode())
            or tentativa["config"] != identidade_config()):
        return HttpResponseBadRequest("Autorização inválida. Inicie uma nova conexão no REGISTER.")
    apagadas, _ = TentativaOAuth.objects.filter(estado_hash=hashlib.sha256(estado.encode()).hexdigest(),
                usuario=request.user, expira_em__gt=timezone.now()).delete()
    if not apagadas:
        return HttpResponseBadRequest("Autorização expirada ou já utilizada. Inicie uma nova conexão.")
    if request.GET.get("error") or not request.GET.get("code"):
        messages.warning(request, "A conexão não foi autorizada no Mercado Livre.")
        return redirect("mercadolivre:painel")
    try:
        conexao = conectar(request.GET["code"], tentativa["verifier"])
    except ErroIntegracao as erro:
        messages.error(request, str(erro))
    else:
        registrar(request.user, "mercadolivre.conectada", conexao.vendedor_id, escopos=conexao.escopos)
        messages.success(request, "Conta conectada. A conexão não publica anúncios; cada publicação exige revisão e confirmação individual." if settings.MERCADOLIVRE_PUBLISH_ENABLED else "Conta conectada em modo somente leitura. Nenhum anúncio foi publicado.")
    return redirect("mercadolivre:painel")


@acesso
@require_POST
def importar(request):
    try:
        total, concluida = importar_lote(reiniciar=request.POST.get("reiniciar") == "sim")
    except ErroIntegracao as erro:
        messages.error(request, str(erro))
    else:
        registrar(request.user, "mercadolivre.importacao", "anuncios", quantidade=total, concluida=concluida)
        messages.success(request, f"{total} anúncio(s) consultado(s). " + ("Importação concluída." if concluida else "Clique em Importar próximo lote para continuar."))
    return redirect("mercadolivre:painel")


@acesso
@require_POST
def desconectar(request):
    with transaction.atomic():
        conexao = Conexao.objects.select_for_update().filter(unica=True).first()
        if conexao:
            conexao.conectada = False
            conexao.access_token_cifrado = conexao.refresh_token_cifrado = conexao.cursor = ""
            conexao.expira_em = conexao.cursor_expira_em = None
            conexao.save()
        TentativaOAuth.objects.all().delete()
        request.session.pop("ml_oauth", None)
        registrar(request.user, "mercadolivre.desconectada", "conexao")
    messages.success(request, "Tokens removidos desta loja. Histórico e vínculos preservados. Para revogar o acesso da aplicação, use também a sua conta no Mercado Livre.")
    return redirect("mercadolivre:painel")


@acesso
@permission_required(("estoque.view_peca", "estoque.change_peca"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def vincular(request, pk):
    anuncio = get_object_or_404(Anuncio.objects.select_related("peca"), pk=pk)
    form = VinculoForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            anuncio = Anuncio.objects.select_for_update().get(pk=pk)
            antes = anuncio.peca_id
            anuncio.peca = form.peca
            anuncio.save(update_fields=["peca"])
            registrar(request.user, "mercadolivre.vinculada", anuncio.item_id, peca_id=form.peca.pk, anterior=antes)
        messages.success(request, "Vínculo local salvo. Estoque, preços e vendas não serão sincronizados nesta etapa.")
        return redirect("mercadolivre:painel")
    return render(request, "mercadolivre/vincular.html", {"anuncio": anuncio, "form": form})


@acesso
@permission_required("estoque.change_peca", raise_exception=True)
@require_POST
def desvincular(request, pk):
    with transaction.atomic():
        anuncio = get_object_or_404(Anuncio.objects.select_for_update(), pk=pk)
        anterior = anuncio.peca_id
        anuncio.peca = None
        anuncio.save(update_fields=["peca"])
        registrar(request.user, "mercadolivre.desvinculada", anuncio.item_id, peca_id=anterior)
    messages.success(request, "Vínculo removido somente no REGISTER.")
    return redirect("mercadolivre:painel")


@acesso
@permission_required(("estoque.view_peca", "estoque.change_peca"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def selecionar(request, pk):
    peca = get_object_or_404(Peca, pk=pk)
    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao not in ("selecionar", "remover"):
            return HttpResponseBadRequest("Escolha uma ação válida.")
        with transaction.atomic():
            Peca.objects.select_for_update().get(pk=pk)
            if acao == "selecionar":
                Selecao.objects.get_or_create(peca=peca, defaults={"usuario": request.user})
            else:
                Selecao.objects.filter(peca=peca).delete()
            registrar(request.user, "mercadolivre.selecao", peca.codigo, selecionada=acao == "selecionar")
        messages.success(request, "Seleção local atualizada. Nenhum anúncio foi enviado ao Mercado Livre.")
        return redirect(reverse("mercadolivre:selecionar", args=[pk]))
    return render(request, "mercadolivre/selecionar.html", {"peca": peca,
        "publicacao_habilitada": settings.MERCADOLIVRE_PUBLISH_ENABLED,
        "publicacao": getattr(peca, "publicacao_ml", None),
        "selecionada": Selecao.objects.filter(peca=peca).exists(), "anuncios": peca.anuncios_mercadolivre.all()})


@acesso
@permission_required(("mercadolivre.publicar_peca", "estoque.view_peca", "estoque.change_peca"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def preparar_publicacao(request, pk):
    from .forms import PublicacaoForm
    from .publicacao import acesso_api, autorizar_publicacao, metadados, preparar, validar_peca
    peca = get_object_or_404(Peca, pk=pk)
    form, categorias, erro, categoria = None, [], "", None
    categoria_id = request.GET.get("categoria", "")
    if not categoria_id and not request.GET.get("trocar_categoria") and "busca" not in request.GET:
        categoria_id = peca.ml_categoria_id
    busca = request.GET.get("busca", peca.nome).strip()[:100]
    try:
        autorizar_publicacao(request.user)
        validar_peca(peca)
        if categoria_id:
            categoria, atributos, tipos = metadados(request.user, categoria_id)
            form = PublicacaoForm(request.POST if request.method == "POST" else None,
                peca=peca, categoria=categoria, atributos=atributos, tipos=tipos)
            if request.method == "POST" and form.is_valid():
                pub = preparar(request.user, peca, form)
                return redirect("mercadolivre:revisar_publicacao", pk=pub.pk)
        elif request.method == "GET":
            _, token, api = acesso_api(request.user)
            categorias = api.enviar("GET", "/sites/MLB/domain_discovery/search", token, q=busca, limit=3)
        else:
            erro = "Escolha a categoria antes de preparar o anúncio."
    except ErroIntegracao as exc:
        erro = str(exc)
    return render(request, "mercadolivre/preparar.html", {"peca": peca, "form": form, "categorias": categorias,
        "categoria": categoria, "busca": busca, "erro": erro})


@acesso
@permission_required(("mercadolivre.publicar_peca", "estoque.view_peca", "estoque.change_peca"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def revisar_publicacao(request, pk):
    from .models import Publicacao
    from .publicacao import confirmar
    pub = get_object_or_404(Publicacao.objects.select_related("peca"), pk=pk, usuario=request.user)
    if request.method == "POST":
        if request.POST.get("confirmacao") != str(pub.pk):
            return HttpResponseBadRequest("Confirme a publicação individual deste anúncio.")
        try:
            confirmar(request.user, pub.pk)
        except ErroIntegracao as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Anúncio criado no Mercado Livre. Confira o resultado abaixo.")
        return redirect("mercadolivre:revisar_publicacao", pk=pub.pk)
    return render(request, "mercadolivre/revisar.html", {"publicacao": pub, "dados": pub.payload,
        "fotos": pub.peca.fotos.filter(pk__in=pub.fotos), "publicacao_habilitada": settings.MERCADOLIVRE_PUBLISH_ENABLED})
