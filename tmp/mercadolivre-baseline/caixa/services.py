from decimal import Decimal, InvalidOperation
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.auditoria import registrar
from .models import SessaoCaixa, MovimentoCaixa


def exigir(usuario, permissao):
    if not usuario.is_active or not usuario.has_perm(permissao):
        raise PermissionDenied


def dinheiro(valor):
    try:
        valor = Decimal(str(valor).replace(",", "."))
        if not valor.is_finite() or valor != valor.quantize(Decimal(".01")) or abs(valor) > Decimal("9999999999.99"):
            raise ValueError
        return valor
    except (ValueError, InvalidOperation, TypeError):
        raise ValidationError("Informe um valor monetário válido, com até duas casas decimais.")


def caixa_aberto(usuario):
    caixa = SessaoCaixa.objects.select_for_update().filter(operador=usuario, fechado_em__isnull=True).first()
    if not caixa:
        raise ValidationError("Abra seu caixa antes de realizar esta operação.")
    return caixa


@transaction.atomic
def abrir(usuario, saldo):
    exigir(usuario, "caixa.operar_caixa")
    get_user_model().objects.select_for_update().get(pk=usuario.pk)
    if SessaoCaixa.objects.filter(operador=usuario, fechado_em__isnull=True).exists():
        raise ValidationError("Você já possui um caixa aberto.")
    saldo = dinheiro(saldo)
    if saldo < 0:
        raise ValidationError("O saldo inicial não pode ser negativo.")
    caixa = SessaoCaixa.objects.create(operador=usuario, saldo_inicial=saldo)
    registrar(usuario, "caixa.abertura", caixa.codigo, saldo=str(saldo))
    return caixa


@transaction.atomic
def movimentar(usuario, tipo, valor, motivo, chave=None):
    exigir(usuario, "caixa.operar_caixa")
    caixa = caixa_aberto(usuario)
    if chave:
        anterior = MovimentoCaixa.objects.filter(chave=chave, operador=usuario).first()
        if anterior:
            return anterior
    valor = dinheiro(valor)
    if tipo not in ["sangria", "suprimento"] or valor <= 0 or not motivo.strip():
        raise ValidationError("Informe tipo, valor positivo e motivo.")
    if tipo == "sangria" and valor > caixa.saldo_esperado:
        raise ValidationError("Sangria maior que o dinheiro disponível no caixa.")
    extras = {"chave": chave} if chave else {}
    movimento = MovimentoCaixa.objects.create(**extras, sessao=caixa, operador=usuario, tipo=tipo,
        valor=-valor if tipo == "sangria" else valor, descricao=motivo.strip()[:240])
    registrar(usuario, f"caixa.{tipo}", caixa.codigo, valor=str(valor), motivo=motivo)
    return movimento


@transaction.atomic
def fechar(usuario, informado, observacoes=""):
    exigir(usuario, "caixa.operar_caixa")
    caixa = caixa_aberto(usuario)
    informado = dinheiro(informado)
    if informado < 0:
        raise ValidationError("O valor contado não pode ser negativo.")
    caixa.saldo_esperado_fechamento = caixa.saldo_esperado
    caixa.saldo_informado = informado
    caixa.fechado_em = timezone.now()
    caixa.observacoes = observacoes
    caixa.save()
    registrar(usuario, "caixa.fechamento", caixa.codigo, esperado=str(caixa.saldo_esperado_fechamento),
        informado=str(informado), diferenca=str(caixa.diferenca), observacoes=observacoes)
    return caixa
