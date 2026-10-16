"""Planejamento financeiro em centavos, sem registrar pagamentos."""
import calendar
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError

FREQUENCIAS = [('semanal', 'Semanal'), ('quinzenal', 'Quinzenal'), ('mensal', 'Mensal'),
               ('bimestral', 'Bimestral'), ('trimestral', 'Trimestral'), ('semestral', 'Semestral'),
               ('anual', 'Anual'), ('dias', 'Intervalo em dias')]


def data_parcela(inicio, indice, frequencia, intervalo=30):
    try:
        if frequencia in ('semanal', 'quinzenal', 'dias'):
            dias = {'semanal': 7, 'quinzenal': 15, 'dias': intervalo}[frequencia]
            if not isinstance(dias, int) or not 1 <= dias <= 3650:
                raise ValueError
            return inicio + timedelta(days=dias * indice)
        meses = dict(mensal=1, bimestral=2, trimestral=3, semestral=6, anual=12)[frequencia]
        ano, mes = divmod(inicio.year * 12 + inicio.month - 1 + meses * indice, 12)
        return inicio.replace(year=ano, month=mes + 1,
                              day=min(inicio.day, calendar.monthrange(ano, mes + 1)[1]))
    except (KeyError, ValueError, OverflowError, TypeError):
        raise ValidationError('Confira a frequência, o intervalo e as datas do parcelamento.')


def valor_monetario(valor):
    try:
        valor = Decimal(str(valor).strip().replace(',', '.'))
        if not valor.is_finite() or valor <= 0 or valor > Decimal('9999999999.99') or valor != valor.quantize(Decimal('.01')):
            raise ValueError
        return valor
    except (InvalidOperation, ValueError):
        raise ValidationError('Informe valores positivos com até duas casas decimais.')


def planejar(total, inicio, quantidade=1, frequencia='mensal', entrada=0,
             data_entrada=None, intervalo=30, personalizado='', forma=None):
    total = valor_monetario(total)
    if not quantidade or not 1 <= quantidade <= 120:
        raise ValidationError('Informe entre 1 e 120 parcelas.')
    if personalizado:
        linhas = [l.strip() for l in personalizado.splitlines() if l.strip()]
        if not 1 <= len(linhas) <= 120:
            raise ValidationError('Informe até 120 parcelas personalizadas.')
        plano = []
        for linha in linhas:
            try:
                campos = linha.split(';')
                if len(campos) not in (2, 3):
                    raise ValueError
                vencimento = date.fromisoformat(campos[0].strip())
                valor = valor_monetario(campos[1])
                forma_id = int(campos[2]) if len(campos) == 3 and campos[2].strip() else forma
                plano.append({'vencimento': vencimento, 'valor': valor, 'forma_id': forma_id})
            except (ValueError, TypeError):
                raise ValidationError('Use uma linha por parcela: AAAA-MM-DD;valor;ID da forma (opcional).')
        if entrada:
            raise ValidationError('No plano personalizado, inclua a entrada como uma das linhas.')
        if sum(p['valor'] for p in plano) != total:
            raise ValidationError('A soma das parcelas precisa corresponder exatamente ao valor total.')
        if plano != sorted(plano, key=lambda p: p['vencimento']):
            raise ValidationError('Informe as parcelas em ordem de vencimento.')
        return plano
    entrada = valor_monetario(entrada) if entrada else Decimal('0')
    if entrada >= total or (entrada and not data_entrada):
        raise ValidationError('Informe a data da entrada e um valor menor que o total.')
    if entrada and data_entrada > inicio:
        raise ValidationError('A entrada deve vencer até a primeira parcela.')
    centavos = int((total - entrada) * 100)
    base, resto = divmod(centavos, quantidade)
    if base < 1 or quantidade + bool(entrada) > 120:
        raise ValidationError('Cada parcela deve ter pelo menos R$ 0,01; limite de 120 lançamentos incluindo entrada.')
    plano = ([{'vencimento': data_entrada, 'valor': entrada, 'forma_id': forma}] if entrada else [])
    return plano + [{'vencimento': data_parcela(inicio, i, frequencia, intervalo),
                     'valor': Decimal(base + (i < resto)) / 100, 'forma_id': forma}
                    for i in range(quantidade)]
