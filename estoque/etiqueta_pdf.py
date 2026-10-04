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

    # =========================================================
    # CÓDIGO DE BARRAS
    # NÃO ALTERAR: tamanho e posição já estão corretos.
    # =========================================================

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

    # =========================================================
    # INFORMAÇÕES DA PEÇA
    #
    # O texto começa imediatamente acima do código de barras.
    # Usamos posições fixas para não acumular espaçamentos.
    # =========================================================

    # ---------------------------------------------------------
    # CÓDIGO DA PEÇA
    # ---------------------------------------------------------

    codigo = f"Cód.: {peca.codigo}"

    pdf.setFont("Helvetica-Bold", 7.5)

    pdf.drawString(
        x,
        9.0 * mm,
        _abreviar(
            codigo,
            util,
            pdf.stringWidth,
            7.5,
        ),
    )

    # ---------------------------------------------------------
    # LADO / POSIÇÃO
    # ---------------------------------------------------------

    linha_posicao = f"Lado/posição: {peca.posicao or '-'}"

    pdf.setFont("Helvetica-Bold", 7)

    pdf.drawString(
        x,
        11.7 * mm,
        _abreviar(
            linha_posicao,
            util,
            pdf.stringWidth,
            7,
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

    linha_ano = f"Ano: {ano}"

    pdf.setFont("Helvetica-Bold", 7)

    pdf.drawString(
        x,
        14.4 * mm,
        _abreviar(
            linha_ano,
            util,
            pdf.stringWidth,
            7,
        ),
    )

    # ---------------------------------------------------------
    # MARCA + MODELO
    # ---------------------------------------------------------

    marca_modelo = (
        f"Marca: {peca.marca or '-'}"
        f" | Modelo: {peca.aplicacao or '-'}"
    )

    pdf.setFont("Helvetica-Bold", 7)

    pdf.drawString(
        x,
        17.1 * mm,
        _abreviar(
            marca_modelo,
            util,
            pdf.stringWidth,
            7,
        ),
    )

    # ---------------------------------------------------------
    # NOME DA PEÇA
    # ---------------------------------------------------------

    nome = " ".join(peca.nome.split())

    pdf.setFont("Helvetica-Bold", 7.5)

    pdf.drawString(
        x,
        19.8 * mm,
        _abreviar(
            nome,
            util,
            pdf.stringWidth,
            7.5,
        ),
    )

    # Exatamente uma página = uma etiqueta.
    pdf.showPage()
    pdf.save()

    return arquivo.getvalue()