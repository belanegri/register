from io import BytesIO
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
from .models import Peca


def gerar_pdf(pecas, consulta="", status=""):
    pecas = list(pecas)
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=28, leftMargin=28,
        topMargin=38, bottomMargin=36, title="PontoCar - Estoque de peças",
        author="PontoCar Comércio de Peças")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="StockCell", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=7, leading=9, spaceAfter=0, wordWrap="LTR"))
    styles.add(ParagraphStyle(name="StockHeader", parent=styles["StockCell"],
        fontName="Helvetica-Bold", textColor=colors.white))

    def cell(value, style="StockCell"):
        return Paragraph(escape(str(value or "—")), styles[style])

    filtros = []
    if consulta:
        filtros.append(f"Busca: {consulta}")
    if status:
        filtros.append(f"Disponibilidade: {dict(Peca.Status.choices).get(status, status)}")
    elementos = [cell("PontoCar Comércio de Peças", "Title"), cell("Estoque de peças", "Heading2"),
        cell("Emitido em " + timezone.localtime().strftime("%d/%m/%Y %H:%M"))]
    if filtros:
        elementos.append(cell("Filtros aplicados: " + " | ".join(filtros)))
    elementos.extend([cell(f"{len(pecas)} cadastro(s) encontrado(s)"), Spacer(1, 10)])

    linhas = [[cell(titulo, "StockHeader") for titulo in
        ["Código", "Peça / categoria", "Aplicação", "Localização", "Qtd.", "Preço", "Situação"]]]
    for peca in pecas:
        aplicacao = " ".join(parte for parte in [peca.marca, peca.aplicacao, peca.posicao] if parte)
        linhas.append([
            cell(peca.codigo),
            cell(f"{peca.nome} / {peca.categoria.nome}"),
            cell(aplicacao),
            cell(peca.localizacao or "Não informada"),
            cell(peca.quantidade),
            cell("R$ " + f"{peca.preco_venda:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")),
            cell(peca.get_status_display()),
        ])
    if pecas:
        pesos = [66, 150, 160, 105, 38, 62, 75]
        tabela = LongTable(linhas, colWidths=[doc.width * peso / sum(pesos) for peso in pesos], repeatRows=1)
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#21654d")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f2")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), .3, colors.HexColor("#dddddd")),
        ]))
        elementos.append(tabela)
    else:
        elementos.append(cell("Nenhuma peça encontrada para os filtros selecionados."))

    def rodape(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#66736b"))
        canvas.drawString(28, 20, "PontoCar | Estoque de peças")
        canvas.drawRightString(document.pagesize[0] - 28, 20, f"Página {document.page}")
        canvas.restoreState()

    doc.build(elementos, onFirstPage=rodape, onLaterPages=rodape)
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="estoque-pecas.pdf"'
    response["Cache-Control"] = "private, no-store"
    return response