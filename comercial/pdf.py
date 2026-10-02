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



def _gerar_pdf_a4_profissional(documento):
    """
    Layout A4 profissional para Orçamento e Ordem de Serviço.
    Mantém os dados e cálculos do Documento e usa uma grade visual única.
    """

    empresa = ConfiguracaoEmpresa.objects.first()

    nome = ""
    if empresa:
        nome = empresa.nome_fantasia or empresa.razao_social or ""
    if not nome:
        nome = "REGISTER"

    w, h = A4
    margem = 13 * mm
    largura = w - (2 * margem)

    # ------------------------------------------------------------
    # ESTILOS
    # ------------------------------------------------------------

    corpo = ParagraphStyle(
        "a4_corpo",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=TEXT,
    )

    pequeno = ParagraphStyle(
        "a4_pequeno",
        parent=corpo,
        fontSize=7.3,
        leading=9.2,
        textColor=MUTED,
    )

    rotulo = ParagraphStyle(
        "a4_rotulo",
        parent=pequeno,
        fontName="Helvetica-Bold",
        fontSize=6.8,
        leading=8,
        textColor=GREEN_DARK,
    )

    secao = ParagraphStyle(
        "a4_secao",
        parent=corpo,
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=GREEN_DARK,
    )

    empresa_style = ParagraphStyle(
        "a4_empresa",
        parent=corpo,
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=13,
        textColor=GREEN_DARK,
    )

    titulo_style = ParagraphStyle(
        "a4_titulo",
        parent=corpo,
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=19,
        alignment=2,
        textColor=GREEN,
    )

    codigo_style_a4 = ParagraphStyle(
        "a4_codigo",
        parent=corpo,
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        alignment=2,
        textColor=TEXT,
    )

    valor_style = ParagraphStyle(
        "a4_valor",
        parent=corpo,
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        alignment=2,
        textColor=TEXT,
    )

    total_label_style = ParagraphStyle(
        "a4_total_label",
        parent=corpo,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=GREEN_DARK,
    )

    total_valor_style = ParagraphStyle(
        "a4_total_valor",
        parent=corpo,
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        alignment=2,
        textColor=GREEN_DARK,
    )

    assinatura_style = ParagraphStyle(
        "a4_assinatura",
        parent=pequeno,
        alignment=1,
        fontSize=7.5,
        leading=10,
    )

    def txt(valor, estilo=corpo):
        return Paragraph(
            escape(str(valor if valor is not None else "")).replace(
                "\n", "<br/>"
            ),
            estilo,
        )

    def campo(label, valor):
        if valor is None or str(valor).strip() == "":
            valor = "—"

        conteudo = [
            txt(label.upper(), rotulo),
            txt(valor, corpo),
        ]

        return conteudo

    def faixa_titulo(titulo):
        tabela = Table(
            [[txt(titulo, secao)]],
            colWidths=[largura],
        )
        tabela.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), PALE),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.7, GREEN),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return tabela

    # ------------------------------------------------------------
    # LOGO E IDENTIDADE
    # ------------------------------------------------------------

    logo = None

    if empresa and empresa.logo:
        try:
            with empresa.logo.open("rb") as f:
                raw = f.read(5 * 1024 * 1024 + 1)

            if len(raw) <= 5 * 1024 * 1024:
                logo = Image(BytesIO(raw))

                max_w = 27 * mm
                max_h = 19 * mm

                ratio = min(
                    max_w / logo.imageWidth,
                    max_h / logo.imageHeight,
                )

                logo.drawWidth = logo.imageWidth * ratio
                logo.drawHeight = logo.imageHeight * ratio

        except (OSError, ValueError):
            logo = None

    empresa_linhas = [txt(nome, empresa_style)]

    if empresa:
        if empresa.razao_social and empresa.razao_social != nome:
            empresa_linhas.append(txt(empresa.razao_social, pequeno))

        documentos_empresa = " • ".join(
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

        if documentos_empresa:
            empresa_linhas.append(txt(documentos_empresa, pequeno))

        endereco_empresa = ", ".join(
            filter(
                None,
                [
                    empresa.endereco,
                    empresa.numero,
                    empresa.complemento,
                ],
            )
        )

        local_empresa = " - ".join(
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

        if endereco_empresa:
            empresa_linhas.append(txt(endereco_empresa, pequeno))

        if local_empresa:
            empresa_linhas.append(txt(local_empresa, pequeno))

        contato_empresa = " • ".join(
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

        if contato_empresa:
            empresa_linhas.append(txt(contato_empresa, pequeno))

    tipo_nome = (
        "ORÇAMENTO"
        if documento.tipo == "orcamento"
        else "ORDEM DE SERVIÇO"
    )

    documento_linhas = [
        txt(tipo_nome, titulo_style),
        txt(documento.codigo, codigo_style_a4),
        txt(
            f"STATUS: {str(documento.situacao).upper()}",
            codigo_style_a4,
        ),
    ]

    if logo:
        cabecalho = Table(
            [[logo, empresa_linhas, documento_linhas]],
            colWidths=[
                30 * mm,
                largura - 92 * mm,
                62 * mm,
            ],
        )
    else:
        cabecalho = Table(
            [[empresa_linhas, documento_linhas]],
            colWidths=[
                largura - 62 * mm,
                62 * mm,
            ],
        )

    cabecalho.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 1, GREEN),
            ]
        )
    )

    fluxo = [
        cabecalho,
        Spacer(1, 4 * mm),
    ]

    # ------------------------------------------------------------
    # CLIENTE
    # ------------------------------------------------------------

    cliente = documento.cliente

    cliente_dados = [
        [
            campo("Cliente", cliente.nome),
            campo("CPF/CNPJ", cliente.documento),
        ],
        [
            campo("Telefone", cliente.telefone),
            campo("E-mail", cliente.email),
        ],
    ]

    if cliente.endereco:
        cliente_dados.append(
            [
                campo("Endereço", cliente.endereco),
                "",
            ]
        )

    cliente_table = Table(
        cliente_dados,
        colWidths=[
            largura * 0.50,
            largura * 0.50,
        ],
    )

    estilo_cliente = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, BORDER),
        ("LINEAFTER", (0, 0), (0, -1), 0.3, BORDER),
    ]

    if cliente.endereco:
        estilo_cliente.append(("SPAN", (0, -1), (-1, -1)))

    cliente_table.setStyle(TableStyle(estilo_cliente))

    fluxo += [
        faixa_titulo("CLIENTE"),
        cliente_table,
        Spacer(1, 3 * mm),
    ]

    # ------------------------------------------------------------
    # VEÍCULO
    # ------------------------------------------------------------

    veiculo_table = Table(
        [
            [
                campo("Veículo", documento.veiculo),
                campo("Placa", documento.placa),
                campo("Ano", documento.ano),
                campo("KM", documento.km),
            ],
            [
                campo("Combustível", documento.combustivel),
                "",
                "",
                "",
            ],
        ],
        colWidths=[
            largura * 0.43,
            largura * 0.19,
            largura * 0.17,
            largura * 0.21,
        ],
    )

    veiculo_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 1), (-1, 1)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LINEAFTER", (0, 0), (-2, 0), 0.3, BORDER),
                ("LINEBELOW", (0, 0), (-1, 0), 0.3, BORDER),
            ]
        )
    )

    fluxo += [
        faixa_titulo("VEÍCULO"),
        veiculo_table,
        Spacer(1, 3 * mm),
    ]

    # ------------------------------------------------------------
    # DATAS
    # ------------------------------------------------------------

    if documento.tipo == "orcamento":
        datas = [
            ("Emissão", data(documento.criado_em)),
            ("Validade", data(documento.validade)),
            ("Situação", documento.situacao),
        ]
    else:
        datas = [
            ("Abertura", data(documento.criado_em)),
            ("Previsão", data(documento.previsao)),
            ("Conclusão", data(documento.conclusao) or "—"),
        ]

    datas_table = Table(
        [[campo(label, valor) for label, valor in datas]],
        colWidths=[largura / len(datas)] * len(datas),
    )

    datas_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEAFTER", (0, 0), (-2, -1), 0.3, BORDER),
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

    # ------------------------------------------------------------
    # ITENS
    # ------------------------------------------------------------

    itens = list(documento.itens.all())

    for tipo, label in [
        ("peca", "PEÇAS / PRODUTOS"),
        ("servico", "SERVIÇOS / MÃO DE OBRA"),
    ]:
        selecionados = [
            item
            for item in itens
            if getattr(item, tipo + "_id")
        ]

        if not selecionados:
            continue

        linhas = [
            [
                txt("QTD", rotulo),
                txt("DESCRIÇÃO", rotulo),
                txt("VALOR UNITÁRIO", rotulo),
                txt("TOTAL", rotulo),
            ]
        ]

        for item in selecionados:
            linhas.append(
                [
                    txt(item.quantidade),
                    txt(item.descricao),
                    txt("R$ " + moeda(item.preco), valor_style),
                    txt("R$ " + moeda(item.total), valor_style),
                ]
            )

        tabela_itens = Table(
            linhas,
            colWidths=[
                largura * 0.08,
                largura * 0.52,
                largura * 0.20,
                largura * 0.20,
            ],
            repeatRows=1,
            splitByRow=1,
        )

        tabela_itens.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, GREEN),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.3, BORDER),
                    ("ALIGN", (0, 1), (0, -1), "CENTER"),
                    ("ALIGN", (-2, 0), (-1, -1), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )

        fluxo += [
            faixa_titulo(label),
            tabela_itens,
            Spacer(1, 3 * mm),
        ]

    # ------------------------------------------------------------
    # RESUMO FINANCEIRO
    # ------------------------------------------------------------

    resumo_dados = [
        [
            txt("Produtos / Peças", corpo),
            txt(
                "R$ " + moeda(documento.subtotal_pecas),
                valor_style,
            ),
        ],
        [
            txt("Serviços / Mão de obra", corpo),
            txt(
                "R$ " + moeda(documento.subtotal_servicos),
                valor_style,
            ),
        ],
    ]

    if documento.desconto:
        resumo_dados.append(
            [
                txt("Desconto", corpo),
                txt(
                    "- R$ " + moeda(documento.desconto),
                    valor_style,
                ),
            ]
        )

    resumo_dados.append(
        [
            txt("TOTAL", total_label_style),
            txt(
                "R$ " + moeda(documento.total),
                total_valor_style,
            ),
        ]
    )

    resumo = Table(
        resumo_dados,
        colWidths=[
            largura * 0.72,
            largura * 0.28,
        ],
    )

    resumo.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, BORDER),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -2), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -2), 5),
                ("BACKGROUND", (0, -1), (-1, -1), PALE),
                ("LINEABOVE", (0, -1), (-1, -1), 1, GREEN),
                ("LINEBELOW", (0, -1), (-1, -1), 1, GREEN),
                ("TOPPADDING", (0, -1), (-1, -1), 7),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
            ]
        )
    )

    fluxo += [
        resumo,
        Spacer(1, 4 * mm),
    ]

    # ------------------------------------------------------------
    # INFORMAÇÕES DA ORDEM DE SERVIÇO
    # ------------------------------------------------------------

    if documento.tipo == "os":
        if documento.responsavel:
            responsavel_table = Table(
                [[
                    campo(
                        "Técnico / Responsável",
                        documento.responsavel,
                    )
                ]],
                colWidths=[largura],
            )

            responsavel_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )

            fluxo += [
                responsavel_table,
                Spacer(1, 3 * mm),
            ]

        for label, valor in [
            ("RELATO DO CLIENTE", documento.relato),
            ("DIAGNÓSTICO", documento.diagnostico),
            ("SERVIÇO SOLICITADO", documento.solicitado),
        ]:
            if not valor:
                continue

            bloco = Table(
                [
                    [txt(label, secao)],
                    [txt(valor, corpo)],
                ],
                colWidths=[largura],
            )

            bloco.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), PALE),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.5, GREEN),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )

            fluxo += [
                bloco,
                Spacer(1, 3 * mm),
            ]

    # ------------------------------------------------------------
    # OBSERVAÇÕES / CONDIÇÕES
    # ------------------------------------------------------------

    for label, valor in [
        ("OBSERVAÇÕES", documento.observacoes),
        ("CONDIÇÕES", documento.condicoes),
    ]:
        if not valor:
            continue

        bloco = Table(
            [
                [txt(label, secao)],
                [txt(valor, corpo)],
            ],
            colWidths=[largura],
        )

        bloco.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), PALE),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, GREEN),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )

        fluxo += [
            bloco,
            Spacer(1, 3 * mm),
        ]

    # ------------------------------------------------------------
    # ASSINATURAS
    # ------------------------------------------------------------

    assinatura_empresa = [
        txt("____________________________________", assinatura_style),
        txt("Responsável da empresa", assinatura_style),
    ]

    assinatura_cliente = [
        txt("____________________________________", assinatura_style),
        txt("Cliente", assinatura_style),
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
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    fluxo += [
        Spacer(1, 10 * mm),
        tabela_assinaturas,
    ]

    # ------------------------------------------------------------
    # RODAPÉ
    # ------------------------------------------------------------

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
        pagesize=A4,
        leftMargin=margem,
        rightMargin=margem,
        topMargin=12 * mm,
        bottomMargin=18 * mm,
    )

    def primeira_pagina(canvas, doc_obj):
        canvas.saveState()
        canvas.setTitle(
            f"{documento.get_tipo_display()} {documento.codigo}"
        )
        canvas.setAuthor(nome)
        canvas.restoreState()

    doc.build(
        fluxo,
        onFirstPage=primeira_pagina,
        onLaterPages=primeira_pagina,
        canvasmaker=lambda *args, **kwargs: Paginas(
            *args,
            rodape=rodape,
            **kwargs,
        ),
    )

    return buffer.getvalue()


def gerar_pdf(documento, termico=False):
    if termico:
        raise ValueError("Impressão 58 mm foi desativada.")
    return _gerar_pdf_a4_profissional(documento)