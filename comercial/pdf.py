"""Commercial documents, generated directly as PDF; no browser print headers."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image
from reportlab.pdfgen.canvas import Canvas
from core.models import ConfiguracaoEmpresa

GREEN = colors.HexColor('#215c49')
PALE = colors.HexColor('#eef4f1')


def moeda(valor):
    return f'{valor:,.2f}'.replace(',', '@').replace('.', ',').replace('@', '.')


class Paginas(Canvas):
    def __init__(self,*args,rodape='',**kwargs):
        super().__init__(*args,**kwargs)
        self.estados=[]
        self.rodape=rodape
    def showPage(self):
        self.estados.append(dict(self.__dict__))
        self._startPage()
    def save(self):
        total=len(self.estados)
        for state in self.estados:
            self.__dict__.update(state)
            self.setFont('Helvetica',7)
            self.setFillColor(colors.HexColor('#56665f'))
            w,h=self._pagesize
            texto=self.rodape
            from reportlab.lib.utils import simpleSplit
            linhas = simpleSplit(texto, 'Helvetica', 7, w-6*mm)
            for i, linha in enumerate(linhas[-2:]):
                self.drawCentredString(w/2,(12-i*3)*mm,linha)
            self.drawCentredString(w/2,5*mm,f'Página {self._pageNumber} de {total}')
            Canvas.showPage(self)
        Canvas.save(self)


def gerar_pdf(documento,termico=False):
    empresa=ConfiguracaoEmpresa.objects.first()
    nome=(empresa.nome_fantasia or empresa.razao_social) if empresa else ''
    dados=[]
    if empresa:
        for texto in [empresa.razao_social if empresa.razao_social != nome else '',
            ('CNPJ/CPF: '+empresa.documento) if empresa.documento else '',
            ('IE: '+empresa.inscricao_estadual) if empresa.inscricao_estadual else '',
            ', '.join(filter(None,[empresa.endereco,empresa.numero,empresa.complemento])),
            ' - '.join(filter(None,[empresa.bairro,empresa.cidade,empresa.estado,empresa.cep])),
            ' / '.join(filter(None,[empresa.telefone,('WhatsApp: '+empresa.whatsapp) if empresa.whatsapp else ''])),empresa.email]:
            if texto: dados.append(texto)
    w,h=(58*mm,220*mm) if termico else A4
    margem=3*mm if termico else 16*mm
    largura=w-2*margem
    normal=ParagraphStyle('body',fontName='Helvetica',fontSize=7 if termico else 9,leading=9 if termico else 13,spaceAfter=4)
    small=ParagraphStyle('small',parent=normal,fontSize=6 if termico else 8,leading=8 if termico else 11)
    titulo=ParagraphStyle('title',parent=normal,fontName='Helvetica-Bold',fontSize=10 if termico else 17,leading=13 if termico else 20,textColor=GREEN)
    section=ParagraphStyle('section',parent=normal,fontName='Helvetica-Bold',textColor=GREEN,spaceBefore=10,spaceAfter=7)
    def p(text,style=normal): return Paragraph(escape(str(text or '')).replace('\n','<br/>'),style)
    logo=None
    if empresa and empresa.logo:
        try:
            with empresa.logo.open('rb') as f: raw=f.read(5*1024*1024+1)
            if len(raw)<=5*1024*1024:
                logo=Image(BytesIO(raw))
                ratio=min((18 if termico else 25)*mm/logo.imageWidth,20*mm/logo.imageHeight)
                logo.drawWidth=logo.imageWidth*ratio
                logo.drawHeight=logo.imageHeight*ratio
        except (OSError,ValueError):
            logo=None
    # Header is measured and repeated on every page, including continued tables.
    identidade=[p(nome,section)] if nome else []
    identidade += [p(t,small) for t in dados]
    identificacao=[p('ORÇAMENTO' if documento.tipo=='orcamento' else 'ORDEM DE SERVIÇO',titulo),p(documento.codigo,normal),p(documento.situacao,small)]
    if termico:
        header=Table([[logo or '',identificacao]],colWidths=[19*mm,largura-19*mm])
        dados_header=[p(nome,small)] + [p(t,small) for t in dados]
    else:
        header=Table([[logo or '',identidade,identificacao]],colWidths=[28*mm,largura-88*mm,60*mm])
        dados_header=[]
    header.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),6)]))
    _,hh=header.wrap(largura,h)
    def cabecalho(canvas,doc):
        canvas.saveState()
        canvas.setTitle(f'{documento.get_tipo_display()} {documento.codigo}')
        canvas.setAuthor(nome or 'REGISTER')
        header.drawOn(canvas,margem,h-8*mm-hh)
        canvas.setStrokeColor(GREEN)
        canvas.line(margem,h-10*mm-hh,w-margem,h-10*mm-hh)
        canvas.restoreState()
    fluxo=list(dados_header)
    cliente=documento.cliente
    fluxo += [p('DADOS DO CLIENTE',section),p(cliente.nome)]
    for label,valor in [('CPF/CNPJ',cliente.documento),('Telefone',cliente.telefone),('E-mail',cliente.email),('Endereço',cliente.endereco)]:
        if valor: fluxo.append(p(f'{label}: {valor}'))
    fluxo.append(p('DADOS DO VEÍCULO',section))
    for label,valor in [('Marca / Modelo',documento.veiculo),('Placa',documento.placa),('Ano',documento.ano),('KM',documento.km),('Combustível',documento.combustivel)]:
        if valor is not None and str(valor): fluxo.append(p(f'{label}: {valor}'))
    itens=list(documento.itens.all())
    for tipo,label,subtotal in [('peca','PEÇAS / PRODUTOS',documento.subtotal_pecas),('servico','SERVIÇOS / MÃO DE OBRA',documento.subtotal_servicos)]:
        fluxo.append(p(label,section))
        linhas=[[p(t,small) for t in (['QTD / DESCRIÇÃO','TOTAL'] if termico else ['QTD','DESCRIÇÃO','UNITÁRIO (R$)','TOTAL (R$)'])]]
        for i in itens:
            if not getattr(i,tipo+'_id'): continue
            linhas.append([p(f'{i.quantidade} x {i.descricao}\nUnit.: R$ {moeda(i.preco)}',small),p(moeda(i.total),small)] if termico else [p(i.quantidade),p(i.descricao),p(moeda(i.preco)),p(moeda(i.total))])
        if len(linhas)==1: linhas.append([p('Sem itens')]+['']*(len(linhas[0])-1))
        widths=[largura*.72,largura*.28] if termico else [largura*.08,largura*.56,largura*.18,largura*.18]
        tabela=Table(linhas,colWidths=widths,repeatRows=1,hAlign='LEFT',splitByRow=1)
        tabela.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.6,GREEN),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#dbe3df')),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        fluxo += [tabela,p(f'Subtotal: R$ {moeda(subtotal)}',section)]
    resumo=Table([[p(label,small),p('R$ '+moeda(valor),section if label == 'TOTAL' else normal)] for label,valor in [('Produtos / Peças',documento.subtotal_pecas),('Serviços / Mão de obra',documento.subtotal_servicos),('Desconto',documento.desconto),('TOTAL',documento.total)]],colWidths=[largura*.65,largura*.35])
    resumo.setStyle(TableStyle([('BACKGROUND',(0,-1),(-1,-1),PALE),('BOX',(0,-1),(-1,-1),1,GREEN),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6)]))
    fluxo += [Spacer(1,5*mm),KeepTogether([resumo])]
    def data(v): return v.strftime('%d/%m/%Y') if v else ''
    campos=[('Emissão / Abertura',data(documento.criado_em)),('Validade',data(documento.validade))] if documento.tipo=='orcamento' else [('Abertura',data(documento.criado_em)),('Previsão',data(documento.previsao)),('Conclusão',data(documento.conclusao)),('Técnico / Responsável',documento.responsavel),('Relato do cliente',documento.relato),('Diagnóstico',documento.diagnostico),('Serviço solicitado',documento.solicitado)]
    campos += [('Observações',documento.observacoes),('Condições',documento.condicoes)]
    for label,valor in campos:
        if valor: fluxo += [p(label.upper(),section),p(valor)]
    assinaturas=[Spacer(1,14*mm),p('____________________________',small),p('Responsável da empresa',small),Spacer(1,9*mm),p('____________________________',small),p('Cliente',small)]
    if not termico:
        assinaturas = [Spacer(1,14*mm),Table([[p('____________________________',small),p('____________________________',small)],[p('Responsável da empresa',small),p('Cliente',small)]],colWidths=[largura/2,largura/2])]
    fluxo.append(KeepTogether(assinaturas))
    rodape=' • '.join(filter(None,[nome,empresa.documento if empresa else '',(empresa.whatsapp or empresa.telefone) if empresa else '']))
    buffer=BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=(w,h),leftMargin=margem,rightMargin=margem,topMargin=hh+14*mm,bottomMargin=16*mm)
    doc.build(fluxo,onFirstPage=cabecalho,onLaterPages=cabecalho,canvasmaker=lambda *a,**k:Paginas(*a,rodape=rodape,**k))
    return buffer.getvalue()
