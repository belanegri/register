from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfdoc
from reportlab.lib.units import mm
from reportlab.graphics.barcode.code128 import Code128


def _abreviar_texto_misto(partes, largura, fonte_largura):
    """
    partes: lista de tuplas (texto, estilo, tamanho)
    Verifica a largura total acumulada e abrevia o último item se necessário.
    """
    largura_total = sum(fonte_largura(t, f, s) for t, f, s in partes)
    if largura_total <= largura:
        return partes

    # Se ultrapassar, ajusta a última string adicionando reticências
    texto_final, fonte_final, tamanho_final = partes[-1]
    while texto_final and (sum(fonte_largura(t, f, s) for t, f, s in partes[:-1]) +
                           fonte_largura(texto_final + "...", fonte_final, tamanho_final)) > largura:
        texto_final = texto_final[:-1]

    partes[-1] = (texto_final.rstrip() + "...", fonte_final, tamanho_final)
    return partes


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

    # Orientação necessária para a POS-58
    pdf.translate(largura, altura)
    pdf.rotate(180)

    # Margem esquerda e largura útil
    x_inicio = 4.5 * mm
    util = 47 * mm

    # Código de barras no rodapé
    barras = Code128(
        str(peca.codigo), barWidth=0.25 * mm, barHeight=7 * mm,
        humanReadable=False, quiet=True, lquiet=2.5 * mm, rquiet=2.5 * mm,
    )
    pdf.saveState()
    pdf.translate(x_inicio, 4.5 * mm)
    pdf.scale(util / barras.width, 1)
    barras.drawOn(pdf, 0, 0)
    pdf.restoreState()

    # Formatação do Ano
    if peca.ano_inicial and peca.ano_final:
        ano = (str(peca.ano_inicial) if peca.ano_inicial == peca.ano_final
               else f"{peca.ano_inicial} a {peca.ano_final}")
    elif peca.ano_inicial:
        ano = f"{peca.ano_inicial}+"
    elif peca.ano_final:
        ano = f"Até {peca.ano_final}"
    else:
        ano = "-"

    # Estrutura com separação exata entre Negrito (Rótulo) e Normal (Valor)
    linhas = [
        # Linha 1: Título completo em negrito
        [
            (str(peca.nome or '-'), "Helvetica-Bold", 8.5)
        ],
        # Linha 2: Marca | Modelo
        [
            ("Marca: ", "Helvetica-Bold", 7),
            (f"{peca.marca or '-'} | ", "Helvetica", 7),
            ("Modelo: ", "Helvetica-Bold", 7),
            (f"{peca.aplicacao or '-'}", "Helvetica", 7),
        ],
        # Linha 3: Ano | Lado/posição
        [
            ("Ano: ", "Helvetica-Bold", 7),
            (f"{ano} | ", "Helvetica", 7),
            ("Lado/posição: ", "Helvetica-Bold", 7),
            (f"{peca.posicao or '-'}", "Helvetica", 7),
        ],
        # Linha 4: Cód.
        [
            ("Cód.: ", "Helvetica-Bold", 7.5),
            (f"{peca.codigo}", "Helvetica", 7.5),
        ],
    ]

    # Posições Y de cada linha na etiqueta
    posicoes_y = [23.5, 19.8, 16.3, 12.8]

    for partes, y_mm in zip(linhas, posicoes_y):
        partes_ajustadas = _abreviar_texto_misto(partes, util, pdf.stringWidth)
        x_atual = x_inicio

        for texto, fonte, tamanho in partes_ajustadas:
            pdf.setFont(fonte, tamanho)
            pdf.drawString(x_atual, y_mm * mm, texto)
            x_atual += pdf.stringWidth(texto, fonte, tamanho)

    pdf.showPage()
    pdf.save()
    return arquivo.getvalue()