from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfdoc
from reportlab.lib.units import mm
from reportlab.graphics.barcode.code128 import Code128


def _abreviar(texto, largura, fonte, tamanho):
    """Mantém letras legíveis; sinaliza texto que não cabe na etiqueta."""
    texto = ' '.join(str(texto).split())
    if fonte(texto, 'Helvetica-Bold', tamanho) <= largura:
        return texto
    while texto and fonte(texto + '...', 'Helvetica-Bold', tamanho) > largura:
        texto = texto[:-1]
    return texto.rstrip() + '...'


def gerar_etiqueta_pdf(peca):
    """Uma etiqueta 57 x 30 mm, no topo, em escala real e sem rotação."""
    arquivo = BytesIO()
    largura, altura = 57 * mm, 30 * mm
    pdf = canvas.Canvas(arquivo, pagesize=(largura, altura), pageCompression=1)
    pdf.setTitle('Etiqueta 57 x 30 mm')
    pdf.setPageRotation(0)
    # PickTrayByPDFSize solicita o tamanho físico ao leitor PDF/driver que o suporta.
    # Um driver configurado como bobina longa ainda precisa do papel personalizado.
    pdf._doc.Catalog.ViewerPreferences = pdfdoc.PDFDictionary({
        'PrintScaling': pdfdoc.PDFName('None'),
        'PickTrayByPDFSize': pdfdoc.PDFtrue,
        'Duplex': pdfdoc.PDFName('Simplex'),
        'PrintArea': pdfdoc.PDFName('MediaBox'),
        'PrintClip': pdfdoc.PDFName('MediaBox'),
    })
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setStrokeColorRGB(0, 0, 0)
    x, util = 2.5 * mm, 52 * mm
    nome = ' '.join(peca.nome.split())
    primeira = nome
    while primeira and pdf.stringWidth(primeira, 'Helvetica-Bold', 9) > util:
        primeira = primeira[:-1]
    if len(primeira) < len(nome) and ' ' in primeira:
        primeira = primeira.rsplit(' ', 1)[0]
    restante = nome[len(primeira):].strip()
    pdf.setFont('Helvetica-Bold', 9)
    pdf.drawString(x, altura - 11, primeira)
    if restante:
        pdf.drawString(x, altura - 20.5, _abreviar(restante, util, pdf.stringWidth, 9))
    if peca.ano_inicial and peca.ano_final:
        ano = str(peca.ano_inicial) if peca.ano_inicial == peca.ano_final else f'{peca.ano_inicial} a {peca.ano_final}'
    elif peca.ano_inicial:
        ano = f'A partir de {peca.ano_inicial}'
    elif peca.ano_final:
        ano = f'Até {peca.ano_final}'
    else:
        ano = '-'
    linhas = [f"Marca: {peca.marca or '-'}", f"Modelo: {peca.aplicacao or '-'}",
              f'Ano: {ano}', f"Lado / posição: {peca.posicao or '-'}"]
    pdf.setFont('Helvetica-Bold', 8)
    y = altura - 29.5
    for linha in linhas:
        pdf.drawString(x, y, _abreviar(linha, util, pdf.stringWidth, 8))
        y -= 8.5
    # O código nunca é abreviado: ele precisa corresponder às barras.
    codigo = f'Cód. da peça: {peca.codigo}'
    texto = pdf.beginText(x, y)
    texto.setFont('Helvetica-Bold', 8)
    texto.setHorizScale(min(100, 100 * util / pdf.stringWidth(codigo, 'Helvetica-Bold', 8)))
    texto.textOut(codigo)
    pdf.drawText(texto)
    barras = Code128(peca.codigo, barWidth=.25 * mm, barHeight=5.5 * mm,
                     humanReadable=False, quiet=True, lquiet=2.5 * mm, rquiet=2.5 * mm)
    fator = min(1, util / barras.width)
    pdf.saveState()
    pdf.translate(x, .7 * mm)
    pdf.scale(fator, 1)
    barras.drawOn(pdf, 0, 0)
    pdf.restoreState()
    pdf.showPage()
    pdf.save()
    return arquivo.getvalue()
