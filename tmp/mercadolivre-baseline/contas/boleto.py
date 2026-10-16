"""Boletos bancários em reais (44/47 dígitos), sem consulta ou serviço externo.

Referência: manual de cobrança Banrisul/FEBRABAN, páginas 42–44:
https://banrisul.com.br/BOB/data/LeiauteBanrisulFebraban_pdr240_v103_23062023.pdf
A validação dos dígitos não comprova autenticidade nem pagamento do boleto.
"""
import re
from datetime import date, timedelta
from decimal import Decimal


class BoletoInvalido(ValueError):
    pass


def somente_numeros(valor):
    texto = str(valor or '').strip()
    if len(texto) > 100 or re.search(r'[^0-9.\s-]', texto):
        raise BoletoInvalido('Use somente números, espaços, pontos ou hífens do boleto.')
    return re.sub(r'[^0-9]', '', texto)


def modulo10(numero):
    soma = 0
    peso = 2

    for caractere in reversed(numero):
        resultado = int(caractere) * peso

        if resultado > 9:
            resultado = (resultado // 10) + (resultado % 10)

        soma += resultado
        peso = 1 if peso == 2 else 2

    resto = soma % 10
    return 0 if resto == 0 else 10 - resto


def modulo11_boleto(numero):
    soma = 0
    peso = 2

    for caractere in reversed(numero):
        soma += int(caractere) * peso

        peso += 1

        if peso > 9:
            peso = 2

    resto = soma % 11
    dv = 11 - resto

    if dv in (0, 10, 11) or dv > 9:
        return 1

    return dv


def linha_digitavel_para_codigo(linha):
    linha = somente_numeros(linha)

    if len(linha) != 47:
        raise BoletoInvalido(
            "A linha digitável bancária deve possuir 47 números."
        )

    campos = (
        (linha[0:9], linha[9]),
        (linha[10:20], linha[20]),
        (linha[21:31], linha[31]),
    )

    for numero, dv in campos:
        if modulo10(numero) != int(dv):
            raise BoletoInvalido(
                "Linha digitável inválida: "
                "dígito verificador incorreto."
            )

    codigo = (
        linha[0:4]
        + linha[32]
        + linha[33:47]
        + linha[4:9]
        + linha[10:20]
        + linha[21:31]
    )

    numero_sem_dv = codigo[:4] + codigo[5:]

    if modulo11_boleto(numero_sem_dv) != int(codigo[4]):
        raise BoletoInvalido(
            "Boleto inválido: "
            "dígito verificador geral incorreto."
        )

    return codigo


def extrair_valor(codigo):
    codigo = somente_numeros(codigo)

    if len(codigo) != 44:
        raise BoletoInvalido(
            "Código de barras bancário deve possuir 44 números."
        )

    centavos = int(codigo[9:19])

    if centavos == 0:
        return None

    return Decimal(centavos) / Decimal("100")


def extrair_vencimento(codigo, ciclo='atual'):
    codigo = somente_numeros(codigo)

    if len(codigo) != 44:
        raise BoletoInvalido(
            "Código de barras bancário deve possuir 44 números."
        )

    fator = int(codigo[5:9])

    if fator == 0:
        return None

    # O código não distingue os ciclos. O usuário pode selecionar o ciclo antigo.
    # Fatores abaixo de 1000 pertencem somente ao ciclo anterior.
    base = date(1997, 10, 7) if ciclo == 'anterior' or fator < 1000 else date(2022, 5, 29)
    return base + timedelta(days=fator)


def codigo_para_linha_digitavel(codigo):
    campos = [codigo[:4] + codigo[19:24], codigo[24:34], codigo[34:44]]
    return ''.join(campo + str(modulo10(campo)) for campo in campos) + codigo[4] + codigo[5:19]


def processar_boleto(valor, ciclo='atual'):
    if ciclo not in ['atual', 'anterior']:
        raise BoletoInvalido('Selecione um ciclo de vencimento válido.')
    numero = somente_numeros(valor)

    if not numero:
        raise BoletoInvalido(
            "Informe o código de barras ou a linha digitável."
        )

    if len(numero) == 48 or (len(numero) == 44 and numero.startswith('8')):
        return processar_arrecadacao(numero)

    if len(numero) == 47:
        linha_digitavel = numero
        codigo_barras = linha_digitavel_para_codigo(numero)

    elif len(numero) == 44:
        codigo_barras = numero

        numero_sem_dv = codigo_barras[:4] + codigo_barras[5:]

        if modulo11_boleto(numero_sem_dv) != int(codigo_barras[4]):
            raise BoletoInvalido(
                "Código de barras inválido: "
                "dígito verificador incorreto."
            )
        linha_digitavel = codigo_para_linha_digitavel(codigo_barras)

    else:
        raise BoletoInvalido(
            f"Foram encontrados {len(numero)} dígitos. "
            "Use 44 dígitos do código de barras, 47 do boleto bancário "
            "ou 48 da conta de consumo. Confira se o código foi copiado inteiro."
        )

    if codigo_barras[:3] == '000' or codigo_barras[3] != '9':
        raise BoletoInvalido('Informe um boleto bancário em reais. Códigos de arrecadação de 48 dígitos não são suportados.')

    return {
        "linha_digitavel": linha_digitavel,
        "codigo_barras": codigo_barras,
        "valor": extrair_valor(codigo_barras),
        "vencimento": extrair_vencimento(codigo_barras, ciclo),
        "banco": codigo_barras[:3],
        "tipo": "Boleto bancário",
        "informacoes": {"Código do banco": codigo_barras[:3], "Moeda": "Real (BRL)",
                        "Fator de vencimento": codigo_barras[5:9], "Campo livre": codigo_barras[19:]},
    }


def modulo11_arrecadacao(numero):
    resto = sum(int(n) * (2 + i % 8) for i, n in enumerate(reversed(numero))) % 11
    return 0 if resto in (0, 1) else 11 - resto


def processar_arrecadacao(numero):
    """FEBRABAN: 4 blocos de 11 dígitos + DV; valor real apenas para 6/8.

    O campo livre tem layouts diferentes por emissor. Não inferimos vencimento,
    CNPJ completo, nome de empresa ou número de documento a partir dele.
    """
    segmentos = {'1': 'Prefeituras', '2': 'Saneamento', '3': 'Energia elétrica e gás',
                 '4': 'Telecomunicações', '5': 'Órgãos governamentais',
                 '6': 'Carnês e demais empresas', '7': 'Multas de trânsito', '9': 'Uso exclusivo do banco'}
    if numero[0] != '8' or numero[1] not in segmentos or numero[2] not in '6789':
        raise BoletoInvalido('Código de arrecadação inválido. Confira os primeiros dígitos.')
    dv = modulo10 if numero[2] in '67' else modulo11_arrecadacao
    if len(numero) == 48:
        blocos = [numero[i:i+12] for i in range(0, 48, 12)]
        if any(dv(b[:11]) != int(b[11]) for b in blocos):
            raise BoletoInvalido('Conta de consumo inválida: dígito verificador de um bloco incorreto.')
        codigo = ''.join(b[:11] for b in blocos)
    else:
        codigo = numero
    if dv(codigo[:3] + codigo[4:]) != int(codigo[3]):
        raise BoletoInvalido('Conta de consumo inválida: dígito verificador geral incorreto.')
    linha = ''.join(codigo[i:i+11] + str(dv(codigo[i:i+11])) for i in range(0, 44, 11))
    valor = Decimal(codigo[4:15]) / 100 if codigo[2] in '68' and int(codigo[4:15]) else None
    return {'codigo_barras': codigo, 'linha_digitavel': linha, 'valor': valor, 'vencimento': None,
            'banco': '', 'tipo': 'Conta de consumo / arrecadação',
            'informacoes': {'Segmento': segmentos[codigo[1]],
                            'Identificador do emissor (não é CNPJ completo)': codigo[15:23] if codigo[1] == '6' else codigo[15:19],
                            'Tipo do valor': 'Valor em reais' if codigo[2] in '68' else 'Referência (não é valor em reais)',
                            'Campo livre': codigo[23:] if codigo[1] == '6' else codigo[19:]}}
