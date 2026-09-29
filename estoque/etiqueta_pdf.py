from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.graphics.barcode.code128 import Code128


def gerar_etiqueta_pdf(peca):
    """Uma página física, sem cabeçalhos adicionados pela impressão HTML."""
    arquivo = BytesIO()
    largura, altura = 57 * mm, 30 * mm
    pdf = canvas.Canvas(arquivo, pagesize=(largura, altura), pageCompression=1)
    pdf.setTitle("Etiqueta")
    pdf.setViewerPreference("PrintScaling", "None")
    if peca.ano_inicial and peca.ano_final:
        ano = str(peca.ano_inicial) if peca.ano_inicial == peca.ano_final else f"{peca.ano_inicial} a {peca.ano_final}"
    elif peca.ano_inicial:
        ano = f"A partir de {peca.ano_inicial}"
    elif peca.ano_final:
        ano = f"Até {peca.ano_final}"
    else:
        ano = "Não informado"
    linhas = [f"<b>{escape(peca.nome)}</b>",
              f"<b>Marca:</b> {escape(peca.marca or 'Não informada')}",
              f"<b>Modelo:</b> {escape(peca.aplicacao or 'Não informado')}",
              f"<b>Ano:</b> {ano}",
              f"<b>Cód. da peça:</b> {escape(peca.codigo)}"]
    tamanho = 7
    while True:
        estilo = ParagraphStyle("etiqueta", fontName="Helvetica", fontSize=tamanho, leading=tamanho * 1.1)
        texto = Paragraph("<br/>".join(linhas), estilo)
        _, altura_texto = texto.wrap(52 * mm, 19 * mm)
        if altura_texto <= 19 * mm or tamanho <= 3:
            break
        tamanho -= .25
    texto.drawOn(pdf, 2.5 * mm, altura - 1 * mm - altura_texto)
    barras = Code128(peca.codigo, barWidth=.25 * mm, barHeight=9 * mm,
                     humanReadable=False, quiet=True, lquiet=2.5 * mm, rquiet=2.5 * mm)
    fator = min(1, 52 * mm / barras.width)
    pdf.saveState()
    pdf.translate(2.5 * mm, 1 * mm)
    pdf.scale(fator, 1)
    barras.drawOn(pdf, 0, 0)
    pdf.restoreState()
    pdf.showPage()
    pdf.save()
    return arquivo.getvalue()
