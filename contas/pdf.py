from core.documentos import identidade_relatorio
from io import BytesIO
from decimal import Decimal
from xml.sax.saxutils import escape
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle


def moeda(valor):
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data(valor):
    return valor.strftime("%d/%m/%Y") if valor else "Não informado"


def gerar_pdf(contas, individual=False, filtros=None):
    empresa = identidade_relatorio()
    contas = list(contas)
    out = BytesIO()
    doc = SimpleDocTemplate(out,pagesize=A4 if individual else landscape(A4),rightMargin=32,leftMargin=32,topMargin=42,bottomMargin=40,
        title="REGISTER - Contas a pagar",author=empresa)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Cell",fontName="Helvetica",fontSize=8,leading=11,spaceAfter=2,wordWrap="LTR"))
    styles.add(ParagraphStyle(name="HeaderCell",parent=styles["Cell"],textColor=colors.white,fontName="Helvetica-Bold"))
    def p(text,style="Cell"):
        return Paragraph(escape(str(text or "—")).replace("\n","<br/>"),styles[style])
    elementos = [p(empresa,"Title"),p("Conta a pagar" if individual else "Relatório de contas a pagar","Heading2"),
        p("Emitido em " + timezone.localtime().strftime("%d/%m/%Y %H:%M")),Spacer(1,12)]
    if individual:
        c = contas[0]
        linhas = [("Conta",c.codigo),("Categoria / identificação",c.titulo),("Fornecedor",c.fornecedor),
            ("Tipo de conta",c.get_tipo_conta_display() or "Não informado"),("Valor",moeda(c.valor)),
            ("Valor pago",moeda(c.valor_pago)),("Saldo",moeda(c.saldo)),("Vencimento",data(c.vencimento)),("Pagamento programado",data(c.data_programada)),
            ("Forma prevista",c.forma_prevista or "Não informada"),("Situação",c.situacao)]
        if c.status == "paga":
            linhas += [("Pagamento realizado",data(c.pago_em)),("Forma utilizada",c.forma_nome),("Registrado por",c.pago_por or "—")]
        tabela = LongTable([[p(k),p(v)] for k,v in linhas],colWidths=[150,doc.width-150],splitInRow=1)
        tabela.setStyle(TableStyle([("BACKGROUND",(0,0),(0,-1),colors.HexColor("#eef3ef")),("VALIGN",(0,0),(-1,-1),"TOP"),("BOTTOMPADDING",(0,0),(-1,-1),9),("TOPPADDING",(0,0),(-1,-1),9),("LINEBELOW",(0,0),(-1,-1),.3,colors.HexColor("#dddddd"))]))
        elementos += [tabela,Spacer(1,14)]
        if c.observacoes:
            elementos += [p("Observações","Heading2"),p(c.observacoes)]
        if c.motivo_cancelamento:
            elementos += [p("Motivo do cancelamento","Heading2"),p(c.motivo_cancelamento)]
        anexos = list(c.anexos.all())
        if anexos:
            elementos.append(p("Comprovantes e links cadastrados","Heading2"))
            for anexo in anexos:
                if anexo.arquivo:
                    elementos.append(p(anexo.get_tipo_display() + ": " + anexo.nome_arquivo))
                if anexo.link:
                    elementos.append(p("Link: " + anexo.link))
            elementos.append(p("Os arquivos dos comprovantes estão disponíveis na página da conta no sistema."))
    else:
        elementos += [p("Filtros aplicados: " + " | ".join(filtros or ["Todas as contas"])),Spacer(1,12)]
        linhas = [[p(v,"HeaderCell") for v in ["Conta","Fornecedor / categoria","Tipo","Vencimento","Programado","Forma prevista","Situação","Valor"]]]
        for c in contas:
            linhas.append([p(c.codigo),p(c.fornecedor+"\n"+c.titulo),p(c.get_tipo_conta_display()),p(data(c.vencimento)),p(data(c.data_programada)),p(c.forma_prevista),p(c.situacao),p(moeda(c.valor))])
        if contas:
            pesos=[65,190,65,70,70,105,75,95]
            tabela=LongTable(linhas,colWidths=[doc.width*x/sum(pesos) for x in pesos],repeatRows=1,splitInRow=1)
            tabela.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#21654d")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f2f5f2")]),("VALIGN",(0,0),(-1,-1),"TOP"),("BOTTOMPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),8)]))
            elementos.append(tabela)
        else:
            elementos.append(p("Nenhuma conta encontrada para os filtros selecionados."))
        elementos += [Spacer(1,14),p(f"{len(contas)} conta(s) | Total: {moeda(sum((c.valor for c in contas),Decimal('0')))}","Heading2")]
        for status,nome in [("pendente","Aguardando / programadas"),("parcial","Parcialmente pagas"),("paga","Pagas"),("cancelada","Canceladas")]:
            elementos.append(p(nome+": "+moeda(sum(((c.saldo if c.em_aberto else c.valor) for c in contas if c.status==status),Decimal("0")))))
    elementos += [Spacer(1,12),p("Documento de controle interno. Não substitui comprovante bancário ou documento fiscal.")]
    def rodape(canvas,document):
        canvas.saveState()
        canvas.setFont("Helvetica",8)
        canvas.setFillColor(colors.HexColor("#66736b"))
        canvas.drawString(32,22,"REGISTER | Contas a pagar")
        canvas.drawRightString(document.pagesize[0]-32,22,f"Página {document.page}")
        canvas.restoreState()
    doc.build(elementos,onFirstPage=rodape,onLaterPages=rodape)
    response=HttpResponse(out.getvalue(),content_type="application/pdf")
    nome=contas[0].codigo if individual else "relatorio-contas-a-pagar"
    response["Content-Disposition"]=f'inline; filename="{nome}.pdf"'
    response["Cache-Control"]="private, no-store"
    return response
