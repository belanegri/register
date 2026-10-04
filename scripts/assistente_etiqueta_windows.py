"""Imprime uma etiqueta 57x30 via ESC/POS RAW, sem formulário do driver."""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pypdfium2 as pdfium
from pypdf import PdfReader
from PIL import Image

DPI = 203
LARGURA_PONTOS = 384
ALTURA_PONTOS = round(30 * DPI / 25.4)


def ler_etiqueta(uri):
    endereco = urlparse(uri)
    if endereco.scheme != 'register-etiqueta' or endereco.netloc != 'imprimir':
        raise ValueError('Protocolo de etiqueta invalido.')
    parametros = parse_qs(endereco.query, strict_parsing=True)
    if set(parametros) != {'pdf'} or len(parametros['pdf']) != 1:
        raise ValueError('Parametro de etiqueta invalido.')
    valor = parametros['pdf'][0]
    if len(valor) > 16000:
        raise ValueError('Etiqueta excede o tamanho permitido.')
    dados = base64.b64decode(valor + '=' * (-len(valor) % 4), altchars=b'-_', validate=True)
    if not dados.startswith(b'%PDF-'):
        raise ValueError('Arquivo de etiqueta invalido.')
    leitor = PdfReader(io.BytesIO(dados))
    if len(leitor.pages) != 1 or leitor.is_encrypted:
        raise ValueError('A etiqueta deve ter uma pagina sem criptografia.')
    pagina = leitor.pages[0]
    largura = float(pagina.mediabox.width) * 25.4 / 72
    altura = float(pagina.mediabox.height) * 25.4 / 72
    if abs(largura - 57) > .2 or abs(altura - 30) > .2:
        raise ValueError('Somente etiquetas de 57 x 30 mm sao permitidas.')
    return dados


def preparar_impressao(dados):
    with pdfium.PdfDocument(dados) as documento:
        pagina = documento[0]
        bitmap = pagina.render(scale=DPI / 72)
        imagem = bitmap.to_pil().convert('L')
        bitmap.close()
        pagina.close()
    # A cabeça térmica tem 384 pontos; o PDF preserva os 5 mm não imprimíveis.
    esquerda = round(5 * DPI / 25.4)
    recorte = imagem.crop((esquerda, 0, esquerda + LARGURA_PONTOS, ALTURA_PONTOS))
    mono = recorte.convert('1', dither=Image.Dither.NONE)
    # ESC/POS usa bit 1 para tinta; Pillow usa bit 0 para preto.
    raster = bytes(valor ^ 255 for valor in mono.tobytes())
    tinta = sum(valor.bit_count() for valor in raster)
    if tinta < 20:
        raise ValueError('Etiqueta sem conteudo imprimivel; envio cancelado.')
        saida = bytearray(b'\x1b@\x1ba\x00')

    largura_bytes = LARGURA_PONTOS // 8

    # Envia a etiqueta inteira em um único raster:
    # 384 pontos de largura x 240 pontos de altura (~30 mm).
    # Evita dividir a etiqueta em vários comandos GS v 0.
    saida.extend(b'\x1dv0\x00')
    saida.extend(largura_bytes.to_bytes(2, 'little'))
    saida.extend(ALTURA_PONTOS.to_bytes(2, 'little'))
    saida.extend(raster)

    return bytes(saida), tinta


def enviar_raw(nome, dados):
    spool = ctypes.WinDLL('winspool.drv', use_last_error=True)
    class Documento(ctypes.Structure):
        _fields_ = [('nome', wintypes.LPWSTR), ('arquivo', wintypes.LPWSTR), ('tipo', wintypes.LPWSTR)]
    spool.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    spool.OpenPrinterW.restype = wintypes.BOOL
    spool.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(Documento)]
    spool.StartDocPrinterW.restype = wintypes.DWORD
    for metodo in ['StartPagePrinter', 'EndPagePrinter', 'EndDocPrinter', 'AbortPrinter', 'ClosePrinter']:
        getattr(spool, metodo).argtypes = [wintypes.HANDLE]
        getattr(spool, metodo).restype = wintypes.BOOL
    spool.WritePrinter.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    spool.WritePrinter.restype = wintypes.BOOL
    handle = wintypes.HANDLE()
    if not spool.OpenPrinterW(nome, ctypes.byref(handle), None):
        raise ctypes.WinError(ctypes.get_last_error())
    iniciado = False
    try:
        documento = Documento('REGISTER - etiqueta direta 30mm', None, 'RAW')
        trabalho = spool.StartDocPrinterW(handle, 1, ctypes.byref(documento))
        if not trabalho:
            raise ctypes.WinError(ctypes.get_last_error())
        iniciado = True
        if not spool.StartPagePrinter(handle):
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_string_buffer(dados)
        posicao = 0
        while posicao < len(dados):
            escrito = wintypes.DWORD()
            if not spool.WritePrinter(handle, ctypes.byref(buffer, posicao), len(dados)-posicao, ctypes.byref(escrito)) or not escrito.value:
                raise ctypes.WinError(ctypes.get_last_error())
            posicao += escrito.value
        if not spool.EndPagePrinter(handle) or not spool.EndDocPrinter(handle):
            raise ctypes.WinError(ctypes.get_last_error())
        iniciado = False
        return trabalho
    finally:
        if iniciado:
            spool.AbortPrinter(handle)
        spool.ClosePrinter(handle)


def imprimir(uri):
    pdf = ler_etiqueta(uri)
    comandos, tinta = preparar_impressao(pdf)
    config = json.loads(Path(__file__).with_name('impressora.json').read_text(encoding='utf-8-sig'))
    if config.get('nome') not in ['POS-58', 'REGISTER - Etiquetas 57x30']:
        raise ValueError('Fila de etiquetas nao configurada.')
    trabalho = enviar_raw(config['nome'], comandos)
    return {'sha256': hashlib.sha256(pdf).hexdigest(), 'trabalho': trabalho,
            'altura_pontos': ALTURA_PONTOS, 'tinta_pontos': tinta, 'impressora': config['nome']}


if __name__ == '__main__':
    arquivo = Path(__file__).with_name('ultimo-trabalho.json')
    registro = {'hora': datetime.now(timezone.utc).isoformat(), 'status': 'recebida'}
    arquivo.write_text(json.dumps(registro), encoding='utf-8')
    try:
        if len(sys.argv) != 2:
            raise ValueError('Uma etiqueta e obrigatoria.')
        registro.update(imprimir(sys.argv[1]), status='enviada')
    except Exception as erro:
        registro.update(status='erro', mensagem=str(erro))
    arquivo.write_text(json.dumps(registro), encoding='utf-8')
    if registro['status'] == 'erro':
        sys.exit(1)
