from io import BytesIO
from decimal import Decimal
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    LongTable,
    Table,
    TableStyle,
    Image,
)

from core.models import ConfiguracaoEmpresa


GREEN = colors.HexColor("#215c49")
DARK = colors.HexColor("#26352f")
PALE = colors.HexColor("#eef4f1")
LIGHT = colors.HexColor("#f7f9f8")
BORDER = colors.HexColor("#d9e1dd")
MUTED = colors.HexColor("#66736b")
RED = colors.HexColor("#a83b3b")
ORANGE = colors.HexColor("#a96818")


def moeda(valor):
    valor = valor or Decimal("0")
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data(valor):
    return valor.strftime("%d/%m/%Y") if valor else "Não informado"


def gerar_pdf(contas, individual=False, filtros=None):
    contas = list(contas)
    empresa = ConfiguracaoEmpresa.objects.first()

    nome_empresa = ""
    if empresa:
        nome_empresa = empresa.nome_fantasia or empresa.razao_social or ""
    if not nome_empresa:
        nome_empresa = "REGISTER"

    out = BytesIO()
    pagina = A4 if individual else landscape(A4)

    doc = SimpleDocTemplate(
        out,
        pagesize=pagina,
        rightMargin=13 * mm,
        leftMargin=13 * mm,
        topMargin=43 * mm,
        bottomMargin=17 * mm,
        title="Contas a Pagar",
        author=nome_empresa,
    )

    styles = getSampleStyleSheet()

    normal = ParagraphStyle(
        "PdfNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5 if individual else 7.5,
        leading=11,
        textColor=DARK,
        spaceAfter=2,
    )

    small = ParagraphStyle(
        "PdfSmall",
        parent=normal,
        fontSize=7,
        leading=9,
        textColor=MUTED,
    )

    empresa_style = ParagraphStyle(
        "PdfEmpresa",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=13,
        textColor=GREEN,
    )

    titulo = ParagraphStyle(
        "PdfTitulo",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=17 if individual else 16,
        leading=20,
        textColor=GREEN,
        alignment=2,
    )

    subtitulo = ParagraphStyle(
        "PdfSubtitulo",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=GREEN,
        spaceBefore=6,
        spaceAfter=5,
    )

    cell = ParagraphStyle(
        "PdfCell",
        parent=normal,
        fontSize=7.5 if not individual else 8.5,
        leading=10,
        wordWrap="LTR",
    )

    header_cell = ParagraphStyle(
        "PdfHeaderCell",
        parent=cell,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    def p(text, style=normal):
        if text is None or text == "":
            text = "—"
        return Paragraph(
            escape(str(text)).replace("\n", "<br/>"),
            style,
        )

    # ------------------------------------------------------------------
    # IDENTIDADE DA EMPRESA
    # ------------------------------------------------------------------

    dados_empresa = []

    if empresa:
        if empresa.razao_social and empresa.razao_social != nome_empresa:
            dados_empresa.append(empresa.razao_social)

        documentos = " • ".join(
            filter(
                None,
                [
                    f"CNPJ/CPF: {empresa.documento}" if empresa.documento else "",
                    f"IE: {empresa.inscricao_estadual}" if empresa.inscricao_estadual else "",
                ],
            )
        )
        if documentos:
            dados_empresa.append(documentos)

        endereco1 = ", ".join(
            filter(
                None,
                [
                    empresa.endereco,
                    empresa.numero,
                    empresa.complemento,
                ],
            )
        )
        if endereco1:
            dados_empresa.append(endereco1)

        endereco2 = " - ".join(
            filter(
                None,
                [
                    empresa.bairro,
                    empresa.cidade,
                    empresa.estado,
                    empresa.cep,
                ],
            )
        )
        if endereco2:
            dados_empresa.append(endereco2)

        contato = " • ".join(
            filter(
                None,
                [
                    empresa.telefone,
                    f"WhatsApp: {empresa.whatsapp}" if empresa.whatsapp else "",
                    empresa.email,
                ],
            )
        )
        if contato:
            dados_empresa.append(contato)

    logo = None

    if empresa and empresa.logo:
        try:
            with empresa.logo.open("rb") as arquivo:
                raw = arquivo.read(5 * 1024 * 1024 + 1)

            if len(raw) <= 5 * 1024 * 1024:
                logo = Image(BytesIO(raw))

                max_w = 25 * mm
                max_h = 20 * mm

                proporcao = min(
                    max_w / logo.imageWidth,
                    max_h / logo.imageHeight,
                )

                logo.drawWidth = logo.imageWidth * proporcao
                logo.drawHeight = logo.imageHeight * proporcao

        except (OSError, ValueError):
            logo = None

    identidade = [p(nome_empresa, empresa_style)]
    identidade += [p(item, small) for item in dados_empresa]

    if individual:
        identificacao = [
            p("CONTA A PAGAR", titulo),
            p(
                contas[0].codigo if contas else "",
                ParagraphStyle(
                    "CodigoDocumento",
                    parent=normal,
                    alignment=2,
                    fontName="Helvetica-Bold",
                ),
            ),
        ]
    else:
        identificacao = [
            p("CONTAS A PAGAR", titulo),
            p(
                "RELATÓRIO FINANCEIRO",
                ParagraphStyle(
                    "TipoRelatorio",
                    parent=small,
                    alignment=2,
                    fontName="Helvetica-Bold",
                ),
            ),
        ]

    largura = pagina[0] - 26 * mm

    if logo:
        header = Table(
            [[logo, identidade, identificacao]],
            colWidths=[28 * mm, largura - 88 * mm, 60 * mm],
        )
    else:
        header = Table(
            [[identidade, identificacao]],
            colWidths=[largura - 60 * mm, 60 * mm],
        )

    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    _, altura_header = header.wrap(largura, pagina[1])

    # ------------------------------------------------------------------
    # CABEÇALHO / RODAPÉ
    # ------------------------------------------------------------------

    def pagina_pdf(canvas, document):
        canvas.saveState()

        largura_pagina, altura_pagina = document.pagesize

        header.drawOn(
            canvas,
            13 * mm,
            altura_pagina - 8 * mm - altura_header,
        )

        canvas.setStrokeColor(GREEN)
        canvas.setLineWidth(0.8)

        canvas.line(
            13 * mm,
            altura_pagina - 10 * mm - altura_header,
            largura_pagina - 13 * mm,
            altura_pagina - 10 * mm - altura_header,
        )

        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)

        rodape = " • ".join(
            filter(
                None,
                [
                    nome_empresa,
                    empresa.documento if empresa else "",
                    (
                        empresa.whatsapp or empresa.telefone
                        if empresa
                        else ""
                    ),
                ],
            )
        )

        canvas.drawString(
            13 * mm,
            7 * mm,
            rodape[:120],
        )

        canvas.drawRightString(
            largura_pagina - 13 * mm,
            7 * mm,
            f"Página {document.page}",
        )

        canvas.restoreState()

    elementos = []

    emitido = timezone.localtime().strftime("%d/%m/%Y às %H:%M")

    # ------------------------------------------------------------------
    # CONTA INDIVIDUAL
    # ------------------------------------------------------------------

    if individual:
        if not contas:
            elementos.append(p("Conta não encontrada."))
        else:
            c = contas[0]

            elementos += [
                p(f"Emitido em {emitido}", small),
                Spacer(1, 4 * mm),
            ]

            # Resumo financeiro
            resumo = Table(
                [
                    [
                        [p("VALOR DA CONTA", small), p(moeda(c.valor), subtitulo)],
                        [p("VALOR PAGO", small), p(moeda(c.valor_pago), subtitulo)],
                        [p("SALDO", small), p(moeda(c.saldo), subtitulo)],
                        [p("SITUAÇÃO", small), p(c.situacao, subtitulo)],
                    ]
                ],
                colWidths=[doc.width / 4] * 4,
            )

            resumo.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), PALE),
                        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )

            elementos += [
                resumo,
                Spacer(1, 5 * mm),
                p("DADOS DA CONTA", subtitulo),
            ]

            linhas = [
                ("Código", c.codigo),
                ("Categoria / identificação", c.titulo),
                ("Fornecedor", c.fornecedor),
                ("Tipo de conta", c.get_tipo_conta_display() or "Não informado"),
                ("Vencimento", data(c.vencimento)),
                ("Pagamento programado", data(c.data_programada)),
                ("Forma prevista", c.forma_prevista or "Não informada"),
                ("Situação", c.situacao),
            ]

            if c.status == "paga":
                linhas += [
                    ("Pagamento realizado", data(c.pago_em)),
                    ("Forma utilizada", c.forma_nome or "Não informada"),
                    ("Registrado por", c.pago_por or "—"),
                ]

            tabela = LongTable(
                [[p(k, cell), p(v, cell)] for k, v in linhas],
                colWidths=[55 * mm, doc.width - 55 * mm],
                splitInRow=1,
            )

            tabela.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, -1), PALE),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ]
                )
            )

            elementos += [tabela]

            if c.observacoes:
                elementos += [
                    Spacer(1, 4 * mm),
                    p("OBSERVAÇÕES", subtitulo),
                    p(c.observacoes),
                ]

            if c.motivo_cancelamento:
                elementos += [
                    Spacer(1, 4 * mm),
                    p("MOTIVO DO CANCELAMENTO", subtitulo),
                    p(c.motivo_cancelamento),
                ]

            anexos = list(c.anexos.all())

            if anexos:
                elementos += [
                    Spacer(1, 4 * mm),
                    p("COMPROVANTES E ANEXOS", subtitulo),
                ]

                for anexo in anexos:
                    if anexo.arquivo:
                        elementos.append(
                            p(
                                f"{anexo.get_tipo_display()}: "
                                f"{anexo.nome_arquivo}"
                            )
                        )

                    if anexo.link:
                        elementos.append(
                            p(f"Link cadastrado: {anexo.link}")
                        )

                elementos += [
                    Spacer(1, 2 * mm),
                    p(
                        "Os arquivos dos comprovantes permanecem disponíveis "
                        "na página da conta no sistema.",
                        small,
                    ),
                ]

    # ------------------------------------------------------------------
    # RELATÓRIO
    # ------------------------------------------------------------------

    else:
        total = sum(
            (c.valor for c in contas),
            Decimal("0"),
        )

        total_aberto = sum(
            (
                c.saldo
                for c in contas
                if c.em_aberto
            ),
            Decimal("0"),
        )

        total_pago = sum(
            (
                c.valor_pago
                for c in contas
            ),
            Decimal("0"),
        )

        elementos += [
            p(f"Emitido em {emitido}", small),
            p(
                "Filtros: " + " | ".join(filtros or ["Todas as contas"]),
                small,
            ),
            Spacer(1, 4 * mm),
        ]

        cards = Table(
            [
                [
                    [p("CONTAS", small), p(str(len(contas)), subtitulo)],
                    [p("VALOR TOTAL", small), p(moeda(total), subtitulo)],
                    [p("VALOR PAGO", small), p(moeda(total_pago), subtitulo)],
                    [p("SALDO EM ABERTO", small), p(moeda(total_aberto), subtitulo)],
                ]
            ],
            colWidths=[doc.width / 4] * 4,
        )

        cards.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), PALE),
                    ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        elementos += [
            cards,
            Spacer(1, 5 * mm),
        ]

        linhas = [
            [
                p(v, header_cell)
                for v in [
                    "CONTA",
                    "FORNECEDOR / CATEGORIA",
                    "TIPO",
                    "VENCIMENTO",
                    "PROGRAMADO",
                    "FORMA PREVISTA",
                    "SITUAÇÃO",
                    "VALOR",
                ]
            ]
        ]

        for c in contas:
            linhas.append(
                [
                    p(c.codigo, cell),
                    p(f"{c.fornecedor}\n{c.titulo}", cell),
                    p(c.get_tipo_conta_display(), cell),
                    p(data(c.vencimento), cell),
                    p(data(c.data_programada), cell),
                    p(c.forma_prevista or "—", cell),
                    p(c.situacao, cell),
                    p(moeda(c.valor), cell),
                ]
            )

        if contas:
            pesos = [65, 190, 65, 70, 70, 105, 80, 95]

            tabela = LongTable(
                linhas,
                colWidths=[
                    doc.width * x / sum(pesos)
                    for x in pesos
                ],
                repeatRows=1,
                splitInRow=1,
            )

            tabela.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, LIGHT],
                        ),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LINEBELOW", (0, 1), (-1, -1), 0.25, BORDER),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )

            elementos.append(tabela)

        else:
            elementos.append(
                p("Nenhuma conta encontrada para os filtros selecionados.")
            )

        elementos += [
            Spacer(1, 5 * mm),
            p("RESUMO POR SITUAÇÃO", subtitulo),
        ]

        status_linhas = []

        for status, nome in [
            ("pendente", "Aguardando / programadas"),
            ("parcial", "Parcialmente pagas"),
            ("paga", "Pagas"),
            ("cancelada", "Canceladas"),
        ]:
            quantidade = len(
                [c for c in contas if c.status == status]
            )

            valor = sum(
                (
                    c.saldo if c.em_aberto else c.valor
                    for c in contas
                    if c.status == status
                ),
                Decimal("0"),
            )

            status_linhas.append(
                [
                    p(nome, cell),
                    p(str(quantidade), cell),
                    p(moeda(valor), cell),
                ]
            )

        status_table = Table(
            status_linhas,
            colWidths=[
                doc.width * 0.60,
                doc.width * 0.15,
                doc.width * 0.25,
            ],
        )

        status_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ]
            )
        )

        elementos.append(status_table)

    elementos += [
        Spacer(1, 6 * mm),
        p(
            "Documento de controle interno. "
            "Não substitui comprovante bancário ou documento fiscal.",
            small,
        ),
    ]

    doc.build(
        elementos,
        onFirstPage=pagina_pdf,
        onLaterPages=pagina_pdf,
    )

    response = HttpResponse(
        out.getvalue(),
        content_type="application/pdf",
    )

    nome = (
        contas[0].codigo
        if individual and contas
        else "relatorio-contas-a-pagar"
    )

    response["Content-Disposition"] = (
        f'inline; filename="{nome}.pdf"'
    )
    response["Cache-Control"] = "private, no-store"

    return response