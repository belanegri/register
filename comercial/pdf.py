"""Documentos comerciais profissionais em PDF."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    Image,
)
from reportlab.pdfgen.canvas import Canvas

from core.models import ConfiguracaoEmpresa


GREEN = colors.HexColor("#215c49")
GREEN_DARK = colors.HexColor("#174637")
PALE = colors.HexColor("#eef4f1")
LIGHT = colors.HexColor("#f7f9f8")
BORDER = colors.HexColor("#d9e3de")
TEXT = colors.HexColor("#27332e")
MUTED = colors.HexColor("#69766f")
WHITE = colors.white


def moeda(valor):
    return f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def data(v):
    return v.strftime("%d/%m/%Y") if v else ""


class Paginas(Canvas):
    def __init__(self, *args, rodape="", **kwargs):
        super().__init__(*args, **kwargs)
        self.estados = []
        self.rodape = rodape

    def showPage(self):
        self.estados.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self.estados)

        for state in self.estados:
            self.__dict__.update(state)

            self.setStrokeColor(BORDER)
            self.setLineWidth(0.4)

            w, h = self._pagesize
            self.line(13 * mm, 13 * mm, w - 13 * mm, 13 * mm)

            self.setFont("Helvetica", 7)
            self.setFillColor(MUTED)

            texto = self.rodape

            if len(texto) > 120:
                texto = texto[:117] + "..."

            self.drawString(
                13 * mm,
                8 * mm,
                texto,
            )

            self.drawRightString(
                w - 13 * mm,
                8 * mm,
                f"Página {self._pageNumber} de {total}",
            )

            Canvas.showPage(self)

        Canvas.save(self)


def gerar_pdf(documento, termico=False):
    empresa = ConfiguracaoEmpresa.objects.first()

    nome = ""
    if empresa:
        nome = empresa.nome_fantasia or empresa.razao_social or ""

    if not nome:
        nome = "REGISTER"

    # ================================================================
    # TAMANHO / MARGENS
    # ================================================================

    w, h = (58 * mm, 220 * mm) if termico else A4
    margem = 3 * mm if termico else 13 * mm
    largura = w - (2 * margem)

    # ================================================================
    # ESTILOS
    # ================================================================

    normal = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=7 if termico else 9,
        leading=9 if termico else 12,
        textColor=TEXT,
        spaceAfter=2,
    )

    small = ParagraphStyle(
        "small",
        parent=normal,
        fontSize=6 if termico else 7.5,
        leading=8 if termico else 9.5,
        textColor=MUTED,
    )

    empresa_nome = ParagraphStyle(
        "empresa",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=8 if termico else 11,
        leading=10 if termico else 13,
        textColor=GREEN_DARK,
    )

    titulo = ParagraphStyle(
        "title",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=10 if termico else 18,
        leading=13 if termico else 21,
        textColor=GREEN,
        alignment=2 if not termico else 0,
    )

    codigo_style = ParagraphStyle(
        "codigo",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=7 if termico else 10,
        leading=9 if termico else 12,
        alignment=2 if not termico else 0,
        textColor=TEXT,
    )

    section = ParagraphStyle(
        "section",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=7 if termico else 8,
        leading=9 if termico else 10,
        textColor=GREEN_DARK,
        spaceBefore=7 if termico else 5,
        spaceAfter=4,
    )

    total_style = ParagraphStyle(
        "total",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=9 if termico else 15,
        leading=11 if termico else 18,
        textColor=GREEN_DARK,
        alignment=2,
    )

    def p(text, style=normal):
        return Paragraph(
            escape(str(text or "")).replace("\n", "<br/>"),
            style,
        )

    # ================================================================
    # LOGO
    # ================================================================

    logo = None

    if empresa and empresa.logo:
        try:
            with empresa.logo.open("rb") as f:
                raw = f.read(5 * 1024 * 1024 + 1)

            if len(raw) <= 5 * 1024 * 1024:
                logo = Image(BytesIO(raw))

                max_w = 18 * mm if termico else 28 * mm
                max_h = 18 * mm if termico else 22 * mm

                ratio = min(
                    max_w / logo.imageWidth,
                    max_h / logo.imageHeight,
                )

                logo.drawWidth = logo.imageWidth * ratio
                logo.drawHeight = logo.imageHeight * ratio

        except (OSError, ValueError):
            logo = None

    # ================================================================
    # DADOS DA EMPRESA
    # ================================================================

    dados = []

    if empresa:
        if empresa.razao_social and empresa.razao_social != nome:
            dados.append(empresa.razao_social)

        documentos = " • ".join(
            filter(
                None,
                [
                    f"CNPJ/CPF: {empresa.documento}"
                    if empresa.documento
                    else "",
                    f"IE: {empresa.inscricao_estadual}"
                    if empresa.inscricao_estadual
                    else "",
                ],
            )
        )

        if documentos:
            dados.append(documentos)

        endereco = ", ".join(
            filter(
                None,
                [
                    empresa.endereco,
                    empresa.numero,
                    empresa.complemento,
                ],
            )
        )

        if endereco:
            dados.append(endereco)

        local = " - ".join(
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

        if local:
            dados.append(local)

        contato = " • ".join(
            filter(
                None,
                [
                    empresa.telefone,
                    f"WhatsApp: {empresa.whatsapp}"
                    if empresa.whatsapp
                    else "",
                    empresa.email,
                ],
            )
        )

        if contato:
            dados.append(contato)

    # ================================================================
    # CABEÇALHO
    # ================================================================

    tipo_nome = (
        "ORÇAMENTO"
        if documento.tipo == "orcamento"
        else "ORDEM DE SERVIÇO"
    )

    identidade = [p(nome, empresa_nome)]
    identidade += [p(item, small) for item in dados]

        # Identificação do documento
    if termico:
        identificacao = [
            p(tipo_nome, titulo),
            p(documento.codigo, codigo_style),
            p(f"Status: {documento.situacao}", small),
        ]
    else:
        status_style = ParagraphStyle(
            "status",
            parent=small,
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            textColor=GREEN_DARK,
            alignment=2,
            spaceBefore=3,
        )

        identificacao = [
            p(tipo_nome, titulo),
            p(documento.codigo, codigo_style),
            p(
                f"STATUS: {str(documento.situacao).upper()}",
                status_style,
            ),
        ]

    if termico:
        header = Table(
            [[logo or "", identificacao]],
            colWidths=[19 * mm, largura - 19 * mm],
        )

        dados_header = [p(nome, empresa_nome)]
        dados_header += [p(item, small) for item in dados]

    else:
        if logo:
            header = Table(
                [[logo, identidade, identificacao]],
                colWidths=[
                    31 * mm,
                    largura - 94 * mm,
                    63 * mm,
                ],
            )
        else:
            header = Table(
                [[identidade, identificacao]],
                colWidths=[
                    largura - 63 * mm,
                    63 * mm,
                ],
            )

        dados_header = []

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

    _, hh = header.wrap(largura, h)

    def cabecalho(canvas, doc):
        canvas.saveState()

        canvas.setTitle(
            f"{documento.get_tipo_display()} {documento.codigo}"
        )
        canvas.setAuthor(nome)

        header.drawOn(
            canvas,
            margem,
            h - 8 * mm - hh,
        )

        canvas.setStrokeColor(GREEN)
        canvas.setLineWidth(0.8)

        canvas.line(
            margem,
            h - 10 * mm - hh,
            w - margem,
            h - 10 * mm - hh,
        )

        canvas.restoreState()

    fluxo = list(dados_header)

    # ================================================================
    # CLIENTE E VEÍCULO
    # ================================================================

    cliente = documento.cliente

    if termico:
        fluxo += [
            p("DADOS DO CLIENTE", section),
            p(cliente.nome),
        ]

        for label, valor in [
            ("CPF/CNPJ", cliente.documento),
            ("Telefone", cliente.telefone),
            ("E-mail", cliente.email),
            ("Endereço", cliente.endereco),
        ]:
            if valor:
                fluxo.append(p(f"{label}: {valor}"))

        fluxo.append(p("DADOS DO VEÍCULO", section))

        for label, valor in [
            ("Marca / Modelo", documento.veiculo),
            ("Placa", documento.placa),
            ("Ano", documento.ano),
            ("KM", documento.km),
            ("Combustível", documento.combustivel),
        ]:
            if valor is not None and str(valor):
                fluxo.append(p(f"{label}: {valor}"))

    else:
        cliente_info = [
            p("DADOS DO CLIENTE", section),
            p(cliente.nome, empresa_nome),
        ]

        if cliente.documento:
            cliente_info.append(
                p(f"CPF/CNPJ: {cliente.documento}", small)
            )

        if cliente.telefone:
            cliente_info.append(
                p(f"Telefone: {cliente.telefone}", small)
            )

        if cliente.email:
            cliente_info.append(
                p(f"E-mail: {cliente.email}", small)
            )

        if cliente.endereco:
            cliente_info.append(
                p(f"Endereço: {cliente.endereco}", small)
            )

        veiculo_info = [
            p("DADOS DO VEÍCULO", section),
        ]

        if documento.veiculo:
            veiculo_info.append(
                p(documento.veiculo, empresa_nome)
            )

        veiculo_detalhes = []

        if documento.placa:
            veiculo_detalhes.append(
                f"Placa: {documento.placa}"
            )

        if documento.ano:
            veiculo_detalhes.append(
                f"Ano: {documento.ano}"
            )

        if veiculo_detalhes:
            veiculo_info.append(
                p(" • ".join(veiculo_detalhes), small)
            )

        veiculo_detalhes2 = []

        if documento.km is not None:
            veiculo_detalhes2.append(
                f"KM: {documento.km}"
            )

        if documento.combustivel:
            veiculo_detalhes2.append(
                f"Combustível: {documento.combustivel}"
            )

        if veiculo_detalhes2:
            veiculo_info.append(
                p(" • ".join(veiculo_detalhes2), small)
            )

        infos = Table(
            [[cliente_info, veiculo_info]],
            colWidths=[
                largura * 0.55,
                largura * 0.45,
            ],
        )

        infos.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                    ("LINEAFTER", (0, 0), (0, -1), 0.5, BORDER),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )

        fluxo += [
            infos,
            Spacer(1, 4 * mm),
        ]

    # ================================================================
    # DATAS PRINCIPAIS
    # ================================================================

    if not termico:
        if documento.tipo == "orcamento":
            datas = [
                ("EMISSÃO", data(documento.criado_em)),
                ("VALIDADE", data(documento.validade)),
                ("SITUAÇÃO", documento.situacao),
            ]
        else:
            datas = [
                ("ABERTURA", data(documento.criado_em)),
                ("PREVISÃO", data(documento.previsao)),
                ("CONCLUSÃO", data(documento.conclusao) or "—"),
            ]

        data_cells = []

        for label, valor in datas:
            data_cells.append(
                [
                    p(label, small),
                    p(valor or "—", normal),
                ]
            )

        datas_table = Table(
            [data_cells],
            colWidths=[largura / len(data_cells)] * len(data_cells),
        )

        datas_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), PALE),
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        fluxo += [
            datas_table,
            Spacer(1, 4 * mm),
        ]

    # ================================================================
    # ITENS
    # ================================================================

    itens = list(documento.itens.all())

    for tipo, label, subtotal in [
        ("peca", "PEÇAS / PRODUTOS", documento.subtotal_pecas),
        ("servico", "SERVIÇOS / MÃO DE OBRA", documento.subtotal_servicos),
    ]:
        selecionados = [
            item
            for item in itens
            if getattr(item, tipo + "_id")
        ]

        if not selecionados and not termico:
            continue

        fluxo.append(p(label, section))

        if termico:
            linhas = [
                [
                    p("QTD / DESCRIÇÃO", small),
                    p("TOTAL", small),
                ]
            ]
        else:
            linhas = [
                [
                    p("QTD", small),
                    p("DESCRIÇÃO", small),
                    p("VALOR UNITÁRIO", small),
                    p("TOTAL", small),
                ]
            ]

        for item in selecionados:
            if termico:
                linhas.append(
                    [
                        p(
                            f"{item.quantidade} x {item.descricao}\n"
                            f"Unit.: R$ {moeda(item.preco)}",
                            small,
                        ),
                        p(
                            "R$ " + moeda(item.total),
                            small,
                        ),
                    ]
                )
            else:
                linhas.append(
                    [
                        p(item.quantidade),
                        p(item.descricao),
                        p("R$ " + moeda(item.preco)),
                        p("R$ " + moeda(item.total)),
                    ]
                )

        if len(linhas) == 1:
            linhas.append(
                [p("Sem itens")]
                + [""] * (len(linhas[0]) - 1)
            )

        widths = (
            [largura * 0.72, largura * 0.28]
            if termico
            else [
                largura * 0.08,
                largura * 0.52,
                largura * 0.20,
                largura * 0.20,
            ]
        )

            tabela.setStyle(
            TableStyle(
                [
                    # Cabeçalho claro e mais legível
                    ("BACKGROUND", (0, 0), (-1, 0), PALE),
                    ("TEXTCOLOR", (0, 0), (-1, 0), GREEN_DARK),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),

                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

                    # Linhas alternadas suaves
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [WHITE, LIGHT],
                    ),

                    # Separadores
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, GREEN),
                    (
                        "LINEBELOW",
                        (0, 1),
                        (-1, -1),
                        0.35,
                        BORDER,
                    ),

                    # Espaçamento
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        6 if termico else 7,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        6 if termico else 7,
                    ),

                    # Valores numéricos
                    ("ALIGN", (-2, 0), (-1, -1), "RIGHT"),
                ]
            )
        )

        fluxo.append(tabela)

        if termico:
            fluxo.append(
                p(
                    f"Subtotal: R$ {moeda(subtotal)}",
                    section,
                )
            )
        else:
            subtotal_table = Table(
                [
                    [
                        "",
                        p("Subtotal", small),
                        p(
                            "R$ " + moeda(subtotal),
                            codigo_style,
                        ),
                    ]
                ],
                colWidths=[
                    largura * 0.60,
                    largura * 0.20,
                    largura * 0.20,
                ],
            )

            subtotal_table.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (-2, 0), (-1, -1), "RIGHT"),
                        ("LINEABOVE", (-2, 0), (-1, 0), 0.4, BORDER),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )

            fluxo += [
                subtotal_table,
                Spacer(1, 2 * mm),
            ]

    # ================================================================
    # RESUMO FINANCEIRO
    # ================================================================

    if termico:
        resumo = Table(
            [
                [
                    p(label, small),
                    p(
                        "R$ " + moeda(valor),
                        total_style if label == "TOTAL" else normal,
                    ),
                ]
                for label, valor in [
                    ("Produtos / Peças", documento.subtotal_pecas),
                    ("Serviços", documento.subtotal_servicos),
                    ("Desconto", documento.desconto),
                    ("TOTAL", documento.total),
                ]
            ],
            colWidths=[
                largura * 0.58,
                largura * 0.42,
            ],
        )

        resumo.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, -1), (-1, -1), PALE),
                    ("BOX", (0, -1), (-1, -1), 0.8, GREEN),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        fluxo += [
            Spacer(1, 3 * mm),
            KeepTogether([resumo]),
        ]

    else:
        # O resumo ocupa somente a lateral direita da página.
        # As larguras internas são calculadas sobre essa área,
        # evitando que a tabela ultrapasse a margem.
        largura_resumo = largura * 0.48

        resumo_dados = [
            [
                p("Produtos / Peças", normal),
                p(
                    "R$ " + moeda(documento.subtotal_pecas),
                    codigo_style,
                ),
            ],
            [
                p("Serviços / Mão de obra", normal),
                p(
                    "R$ " + moeda(documento.subtotal_servicos),
                    codigo_style,
                ),
            ],
        ]

        if documento.desconto:
            resumo_dados.append(
                [
                    p("Desconto", normal),
                    p(
                        "- R$ " + moeda(documento.desconto),
                        codigo_style,
                    ),
                ]
            )

        resumo_dados.append(
            [
                p("TOTAL", empresa_nome),
                p(
                    "R$ " + moeda(documento.total),
                    total_style,
                ),
            ]
        )

        resumo = Table(
            resumo_dados,
            colWidths=[
                largura_resumo * 0.56,
                largura_resumo * 0.44,
            ],
            hAlign="RIGHT",
        )

        resumo.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

                    (
                        "LINEBELOW",
                        (0, 0),
                        (-1, -2),
                        0.35,
                        BORDER,
                    ),

                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),

                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -2), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -2), 5),

                    # Linha TOTAL
                    ("BACKGROUND", (0, -1), (-1, -1), PALE),
                    ("BOX", (0, -1), (-1, -1), 0.8, GREEN),
                    ("LINEABOVE", (0, -1), (-1, -1), 1.0, GREEN),
                    ("TOPPADDING", (0, -1), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
                ]
            )
        )

        bloco_resumo = Table(
            [["", resumo]],
            colWidths=[
                largura - largura_resumo,
                largura_resumo,
            ],
        )

        bloco_resumo.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

        fluxo += [
            Spacer(1, 3 * mm),
            KeepTogether([bloco_resumo]),
            Spacer(1, 3 * mm),
        ]

    # ================================================================
    # INFORMAÇÕES DO ORÇAMENTO / OS
    # ================================================================

    if documento.tipo == "os":
        if documento.responsavel:
            if termico:
                fluxo += [
                    p("TÉCNICO / RESPONSÁVEL", section),
                    p(documento.responsavel),
                ]
            else:
                fluxo += [
                    p(
                        f"<b>Técnico / Responsável:</b> "
                        f"{escape(str(documento.responsavel))}",
                        normal,
                    )
                ]

        campos = [
            ("RELATO DO CLIENTE", documento.relato),
            ("DIAGNÓSTICO", documento.diagnostico),
            ("SERVIÇO SOLICITADO", documento.solicitado),
        ]

        for label, valor in campos:
            if not valor:
                continue

            if termico:
                fluxo += [
                    p(label, section),
                    p(valor),
                ]
            else:
                bloco = Table(
                    [
                        [p(label, section)],
                        [p(valor)],
                    ],
                    colWidths=[largura],
                )

                bloco.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), PALE),
                            ("BOX", (0, 0), (-1, -1), 0.4, BORDER),
                            ("LEFTPADDING", (0, 0), (-1, -1), 7),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ]
                    )
                )

                fluxo += [
                    Spacer(1, 2 * mm),
                    bloco,
                ]

    # ================================================================
    # OBSERVAÇÕES E CONDIÇÕES
    # ================================================================

    for label, valor in [
        ("OBSERVAÇÕES", documento.observacoes),
        ("CONDIÇÕES", documento.condicoes),
    ]:
        if not valor:
            continue

        if termico:
            fluxo += [
                p(label, section),
                p(valor),
            ]
        else:
            bloco = Table(
                [
                    [p(label, section)],
                    [p(valor)],
                ],
                colWidths=[largura],
            )

            bloco.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), PALE),
                        ("BOX", (0, 0), (-1, -1), 0.4, BORDER),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )

            fluxo += [
                Spacer(1, 2 * mm),
                bloco,
            ]

    # ================================================================
    # ASSINATURAS
    # ================================================================

    if termico:
        assinaturas = [
            Spacer(1, 14 * mm),
            p("____________________________", small),
            p("Responsável da empresa", small),
            Spacer(1, 9 * mm),
            p("____________________________", small),
            p("Cliente", small),
        ]

        else:
        assinatura_style = ParagraphStyle(
            "assinatura",
            parent=small,
            fontSize=7.5,
            leading=10,
            alignment=1,
            textColor=MUTED,
        )

        assinatura_empresa = [
            p("____________________________________", assinatura_style),
            p("Responsável da empresa", assinatura_style),
        ]

        assinatura_cliente = [
            p("____________________________________", assinatura_style),
            p("Cliente", assinatura_style),
        ]

        tabela_assinaturas = Table(
            [[assinatura_empresa, assinatura_cliente]],
            colWidths=[
                largura * 0.50,
                largura * 0.50,
            ],
        )

        tabela_assinaturas.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

        assinaturas = [
            Spacer(1, 7 * mm),
            tabela_assinaturas,
        ]
    # ================================================================
    # RODAPÉ
    # ================================================================

    rodape = " • ".join(
        filter(
            None,
            [
                nome,
                empresa.documento if empresa else "",
                (
                    empresa.whatsapp or empresa.telefone
                    if empresa
                    else ""
                ),
            ],
        )
    )

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=(w, h),
        leftMargin=margem,
        rightMargin=margem,
        topMargin=hh + 14 * mm,
        bottomMargin=18 * mm if not termico else 16 * mm,
    )

    doc.build(
        fluxo,
        onFirstPage=cabecalho,
        onLaterPages=cabecalho,
        canvasmaker=lambda *args, **kwargs: Paginas(
            *args,
            rodape=rodape,
            **kwargs,
        ),
    )

    return buffer.getvalue()