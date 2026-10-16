"""Consulta das promissórias existentes, sem duplicar cobranças ou recebimentos."""
from decimal import Decimal
from datetime import date
from django.core.paginator import Paginator
from django.db.models import Sum, Value, DecimalField, F, Q
from django.db.models.functions import Coalesce
from vendas.models import NotaPromissoria


def contexto_promissorias(usuario, parametros):
    if not usuario.has_perm('vendas.view_venda'):
        return {}
    from vendas.views import vendas_permitidas
    zero = Value(Decimal('0'), output_field=DecimalField(max_digits=12,decimal_places=2))
    qs = NotaPromissoria.objects.filter(pagamento__venda__in=vendas_permitidas(usuario)).select_related(
        'pagamento__venda__cliente').annotate(abatido=Coalesce(Sum('movimentos__valor'),zero),
        recebido_financeiro=Coalesce(Sum('movimentos__valor',filter=Q(movimentos__tipo='recebido')),zero))
    qs = qs.annotate(saldo_financeiro=F('pagamento__valor')-F('abatido'))
    status = parametros.get('status','')
    from django.utils import timezone
    hoje = timezone.localdate()
    if status == 'canceladas':
        qs = qs.filter(pagamento__venda__status__in=['cancelada','devolvida'])
    else:
        qs = qs.exclude(pagamento__venda__status__in=['cancelada','devolvida'])
    if status == 'vencidas': qs=qs.filter(vencimento__lt=hoje,saldo_financeiro__gt=0)
    elif status == 'vencer': qs=qs.filter(vencimento__gte=hoje,saldo_financeiro__gt=0)
    elif status == 'recebidas': qs=qs.filter(saldo_financeiro=0)
    elif status == 'parciais': qs=qs.filter(recebido_financeiro__gt=0,saldo_financeiro__gt=0)
    for nome,lookup in [('inicio','gte'),('fim','lte')]:
        try:
            if parametros.get(nome): qs=qs.filter(**{'vencimento__'+lookup:date.fromisoformat(parametros[nome])})
        except ValueError:
            qs=qs.none()
    busca=parametros.get('q','').strip()[:240]
    if busca:
        qs=qs.filter(Q(emitente__icontains=busca)|Q(documento__icontains=busca)|Q(pagamento__venda__cliente__nome__icontains=busca))
    pagina=Paginator(qs.order_by('vencimento','pk'),30).get_page(parametros.get('promissoria_page'))
    links=parametros.copy();links.pop('promissoria_page',None)
    return {'pagina_promissorias':pagina,'saldo_promissorias':qs.aggregate(s=Sum('saldo_financeiro'))['s'] or 0,
            'parametros_promissorias':links.urlencode()}
