"""Leitura local do BR Code. Não consulta URLs, DICT nem executa pagamentos.

Referência: Manual de Padrões para Iniciação do Pix, Banco Central.
https://www.bcb.gov.br/content/estabilidadefinanceira/pix/Regulamento_Pix/II_ManualdePadroesparaIniciacaodoPix.pdf
"""
import binascii
import re
from decimal import Decimal


class PixInvalido(ValueError):
    pass


def campos_tlv(texto):
    campos, pos = {}, 0
    while pos < len(texto):
        cabecalho = texto[pos:pos+4]
        if not re.fullmatch(r'[0-9]{4}', cabecalho):
            raise PixInvalido('PIX incompleto ou com estrutura inválida. Copie o código inteiro.')
        chave, tamanho = cabecalho[:2], int(cabecalho[2:])
        fim = pos + 4 + tamanho
        if fim > len(texto) or chave in campos:
            raise PixInvalido('PIX com campos truncados ou repetidos. Copie novamente do documento.')
        campos[chave] = texto[pos+4:fim]
        pos = fim
    return campos


def processar_pix(texto):
    codigo = str(texto or '').strip().replace('\r', '').replace('\n', '')
    if len(codigo) > 4096 or len(codigo) < 20 or any(ord(c) < 32 for c in codigo):
        raise PixInvalido('Informe o PIX Copia e Cola completo, não apenas a chave PIX.')
    campos = campos_tlv(codigo)
    if not re.fullmatch(r'6304[0-9a-fA-F]{4}', codigo[-8:]):
        raise PixInvalido('PIX sem código de verificação válido no final.')
    if binascii.crc_hqx(codigo[:-4].encode('utf-8'), 0xffff) != int(codigo[-4:], 16):
        raise PixInvalido('PIX inválido: código de verificação incorreto. Confira a cópia completa.')
    if campos.get('00') != '01' or campos.get('53') != '986' or campos.get('58') != 'BR':
        raise PixInvalido('O código não é um PIX em reais no padrão BR Code.')
    contas = [campos_tlv(v) for k, v in campos.items() if 26 <= int(k) <= 51]
    contas = [c for c in contas if c.get('00', '').lower() == 'br.gov.bcb.pix']
    if len(contas) != 1:
        raise PixInvalido('Não foi possível identificar uma única cobrança PIX neste código.')
    conta = contas[0]
    if bool(conta.get('01')) == bool(conta.get('25')):
        raise PixInvalido('PIX sem chave ou endereço de cobrança inequívoco.')
    valor = None
    if '54' in campos:
        if not re.fullmatch(r'[0-9]{1,10}(?:\.[0-9]{1,2})?', campos['54']):
            raise PixInvalido('O valor informado no PIX é inválido.')
        valor = Decimal(campos['54'])
        if valor <= 0:
            valor = None
    adicional = campos_tlv(campos['62']) if '62' in campos else {}
    txid = adicional.get('05', '')
    nome = campos.get('59', '').strip()
    informacoes = {'Tipo de PIX': 'Dinâmico' if '25' in conta else 'Estático',
                   'Nome informado no PIX (não verificado no banco)': nome,
                   'Cidade': campos.get('60', ''), 'Identificador da transação (TXID)': txid,
                   'Chave PIX': conta.get('01', ''), 'Informação adicional': conta.get('02', ''),
                   'Endereço da cobrança (não consultado)': conta.get('25', '')}
    avisos = ['Confira o favorecido no documento. O nome contido no código não é uma confirmação bancária.']
    if '25' in conta:
        avisos.append('PIX dinâmico: valor e vencimento podem existir somente no banco. Nenhum endereço externo foi consultado.')
    return {'pix_copia_cola': codigo, 'valor': valor, 'fornecedor': nome,
            'descricao': conta.get('02', ''), 'vencimento': None,
            'informacoes': {k: v for k, v in informacoes.items() if v}, 'avisos': avisos}
