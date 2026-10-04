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


def gerar_etiqueta_pdf(peca):
    """
    Gera exatamente uma etiqueta física de 57 x 30 mm
    para impressão direta na POS-58.
    """

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

    # Impede o leitor/driver de redimensionar a página.
    pdf._doc.Catalog.ViewerPreferences = pdfdoc.PDFDictionary({
        "PrintScaling": pdfdoc.PDFName("None"),
        "PickTrayByPDFSize": pdfdoc.PDFtrue,
        "Duplex": pdfdoc.PDFName("Simplex"),
        "PrintArea": pdfdoc.PDFName("MediaBox"),
        "PrintClip": pdfdoc.PDFName("MediaBox"),
    })

    pdf.setFillColorRGB(0, 0, 0)
    pdf.setStrokeColorRGB(0, 0, 0)

    # Mantém a orientação necessária para a POS-58.
    pdf.translate(largura, altura)
    pdf.rotate(180)

    # Área útil da impressão.
    # Mantemos os limites já medidos para a POS-58.
    x = 4.5 * mm
    util = 47 * mm

    # ---------------------------------------------------------
    # NOME DA PEÇA
    # ---------------------------------------------------------

    nome = " ".join(peca.nome.split())

    pdf.setFont("Helvetica-Bold", 10)

    nome = _abreviar(
        nome,
        util,
        pdf.stringWidth,
        10,
    )

    # Uma única linha.
    # A próxima informação começa imediatamente abaixo.
    y = altura - 6

    pdf.drawString(
        x,
        y,
        nome,
    )

    # ---------------------------------------------------------
    # MARCA + MODELO
    # ---------------------------------------------------------

    y -= 6

    marca_modelo = (
        f"Marca: {peca.marca or '-'}"
        f" | Modelo: {peca.aplicacao or '-'}"
    )

    pdf.setFont("Helvetica-Bold", 8)

    pdf.drawString(
        x,
        y,
        _abreviar(
            marca_modelo,
            util,
            pdf.stringWidth,
            8,
        ),
    )

    # ---------------------------------------------------------
    # ANO
    # ---------------------------------------------------------

    if peca.ano_inicial and peca.ano_final:

        if peca.ano_inicial == peca.ano_final:
            ano = str(peca.ano_inicial)
        else:
            ano = f"{peca.ano_inicial} a {peca.ano_final}"

    elif peca.ano_inicial:

        ano = f"{peca.ano_inicial}+"

    elif peca.ano_final:

        ano = f"Até {peca.ano_final}"

    else:

        ano = "-"

    # ---------------------------------------------------------
    # ANO
    # ---------------------------------------------------------

    y -= 6

    linha_ano = f"Ano: {ano}"

    pdf.setFont("Helvetica-Bold", 8)

    pdf.drawString(
        x,
        y,
        _abreviar(
            linha_ano,
            util,
            pdf.stringWidth,
            8,
        ),
    )

    # ---------------------------------------------------------
    # LADO / POSIÇÃO
    # ---------------------------------------------------------

    y -= 6

    linha_posicao = f"Lado/posição: {peca.posicao or '-'}"

    pdf.drawString(
        x,
        y,
        _abreviar(
            linha_posicao,
            util,
            pdf.stringWidth,
            8,
        ),
    )

    # ---------------------------------------------------------
    # CÓDIGO DA PEÇA
    # ---------------------------------------------------------

    y -= 6
    codigo = f"Cód.: {peca.codigo}"

    texto = pdf.beginText(x, y)

    texto.setFont(
        "Helvetica-Bold",
        9,
    )

    largura_codigo = pdf.stringWidth(
        codigo,
        "Helvetica-Bold",
        9,
    )

    if largura_codigo > 0:
        escala = min(
            100,
            100 * util / largura_codigo,
        )
    else:
        escala = 100

    texto.setHorizScale(escala)

    texto.textOut(codigo)

    pdf.drawText(texto)

    # ---------------------------------------------------------
    # CÓDIGO DE BARRAS
    # ---------------------------------------------------------

    barras = Code128(
        str(peca.codigo),
        barWidth=0.25 * mm,
        barHeight=7 * mm,
        humanReadable=False,
        quiet=True,
        lquiet=2.5 * mm,
        rquiet=2.5 * mm,
    )

    fator = util / barras.width

    pdf.saveState()

    pdf.translate(
        x,
        0.8 * mm,
    )

    pdf.scale(
        fator,
        1,
    )

    barras.drawOn(
        pdf,
        0,
        0,
    )

    pdf.restoreState()

    # Exatamente uma página = uma etiqueta.
    pdf.showPage()
    pdf.save()

    return arquivo.getvalue()