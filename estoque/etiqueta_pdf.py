from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfdoc
from reportlab.lib.units import mm
from reportlab.graphics.barcode.code128 import Code128


def _abreviar(texto, largura, fonte, tamanho):
    """Abrevia somente quando o texto ultrapassa a largura disponível."""
    texto = " ".join(str(texto).split())

    if fonte(texto, "Helvetica-Bold", tamanho) <= largura:
        return texto

    while texto and fonte(
        texto + "...",
        "Helvetica-Bold",
        tamanho,
    ) > largura:
        texto = texto[:-1]

    return texto.rstrip() + "..."


def gerar_etiqueta_pdf(peca, modelo="padrao"):
    """
    Gera exatamente uma etiqueta física de 57 x 30 mm
    para impressão direta na POS-58.
    """

    if modelo not in {"padrao", "online"}:
        raise ValueError("Modelo de etiqueta inválido.")
    arquivo = BytesIO()

    largura = 57 * mm
    altura = 30 * mm

    pdf = canvas.Canvas(
        arquivo,
        pagesize=(largura, altura),
        pageCompression=1,
    )

    pdf.setTitle("Etiqueta 57 x 30 mm")
    pdf.setPageRotation(0)

    pdf._doc.Catalog.ViewerPreferences = pdfdoc.PDFDictionary({
        "PrintScaling": pdfdoc.PDFName("None"),
        "PickTrayByPDFSize": pdfdoc.PDFtrue,
        "Duplex": pdfdoc.PDFName("Simplex"),
        "PrintArea": pdfdoc.PDFName("MediaBox"),
        "PrintClip": pdfdoc.PDFName("MediaBox"),
    })

    pdf.setFillColorRGB(0, 0, 0)
    pdf.setStrokeColorRGB(0, 0, 0)

    # Orientação necessária para a POS-58.
    pdf.translate(largura, altura)
    pdf.rotate(180)

    # Área útil já calibrada para a impressora.
    x = 4.5 * mm
    util = 47 * mm

    if modelo == "online":
        pdf.setFont("Helvetica-Bold", 10)
        for texto, y in [("ESTA PEÇA ESTÁ NO", 19),
                         ("CATÁLOGO DE", 14.5),
                         ("VENDAS ONLINE", 10)]:
            pdf.drawCentredString(x + util / 2, y * mm, texto)
        pdf.showPage()
        pdf.save()
        return arquivo.getvalue()

    # Bloco de quatro linhas e barras centralizado na etiqueta.
    # Mantém a largura e a altura das barras já calibradas.
    barras = Code128(
        str(peca.codigo), barWidth=0.25 * mm, barHeight=7 * mm,
        humanReadable=False, quiet=True, lquiet=2.5 * mm, rquiet=2.5 * mm,
    )
    pdf.saveState()
    pdf.translate(x, 6 * mm)
    pdf.scale(util / barras.width, 1)
    barras.drawOn(pdf, 0, 0)
    pdf.restoreState()

    if peca.ano_inicial and peca.ano_final:
        ano = (str(peca.ano_inicial) if peca.ano_inicial == peca.ano_final
               else f"{peca.ano_inicial} a {peca.ano_final}")
    elif peca.ano_inicial:
        ano = f"{peca.ano_inicial}+"
    elif peca.ano_final:
        ano = f"Até {peca.ano_final}"
    else:
        ano = "-"

    linhas = [
        (peca.nome, 7.5),
        (f"Marca: {peca.marca or '-'} | Modelo: {peca.aplicacao or '-'}", 7),
        (f"Ano: {ano} | Lado/posição: {peca.posicao or '-'}", 7),
        (f"Cód.: {peca.codigo}", 7.5),
    ]
    for indice, (texto, tamanho) in enumerate(linhas):
        pdf.setFont("Helvetica-Bold", tamanho)
        pdf.drawString(x, (22.4 - indice * 2.8) * mm,
                       _abreviar(texto, util, pdf.stringWidth, tamanho))

    pdf.showPage()
    pdf.save()
    return arquivo.getvalue()
