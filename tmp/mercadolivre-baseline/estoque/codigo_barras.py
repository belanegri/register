from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib.units import mm


def gerar_svg(codigo):
    """Code 128 vetorial: não grava imagens nem usa serviços externos."""
    if not codigo or any(ord(c) < 32 or ord(c) > 126 for c in codigo):
        raise ValueError("O código deve conter apenas caracteres imprimíveis ASCII.")
    desenho = createBarcodeDrawing("Code128", value=codigo, barWidth=0.25 * mm,
        barHeight=10 * mm, humanReadable=False, quiet=True, lquiet=2.5 * mm, rquiet=2.5 * mm)
    return desenho.asString("svg")
