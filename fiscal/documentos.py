from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.graphics.barcode.code128 import Code128
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing


def gerar_auxiliar(doc):
    arquivo=BytesIO(); nfce=doc.modelo=='65'
    largura=58*mm if nfce else 210*mm
    altura=max(150,110+len(doc.snapshot.get('itens',[]))*16)*mm if nfce else 297*mm
    pdf=SimpleDocTemplate(arquivo,pagesize=(largura,altura),leftMargin=3*mm if nfce else 12*mm,
        rightMargin=3*mm if nfce else 12*mm,topMargin=5*mm,bottomMargin=5*mm)
    estilos=getSampleStyleSheet(); estilo=estilos['Normal'];estilo.fontSize=7 if nfce else 9;estilo.leading=10 if nfce else 13
    titulo=estilos['Heading2'];titulo.fontSize=10 if nfce else 14
    p=lambda t:Paragraph(escape(str(t)),estilo)
    empresa=doc.snapshot.get('empresa',{})
    nome='DANFE NFC-e' if nfce else ('Documento auxiliar NFS-e' if doc.modelo=='nfse' else 'DANFE')
    partes=[Paragraph(nome,titulo),p(empresa.get('razao_social','')),p('CNPJ: '+empresa.get('cnpj','')),
        p(f'{doc.get_modelo_display()} · Série {doc.serie} · Nº {doc.numero}'),p(doc.get_status_display())]
    if doc.numero_nfse:partes.append(p('Número da NFS-e autorizada: '+doc.numero_nfse))
    if doc.ambiente=='homologacao' or doc.status!='autorizada':
        partes += [Paragraph('SEM VALOR FISCAL — HOMOLOGAÇÃO OU DOCUMENTO NÃO AUTORIZADO',titulo)]
    partes += [p('Emissão: '+doc.emitido_em.strftime('%d/%m/%Y %H:%M')),p('Natureza: '+empresa.get('natureza_operacao',''))]
    partes += [p('Destinatário: '+doc.snapshot.get('destinatario',{}).get('nome','Consumidor')),Spacer(1,3*mm)]
    linhas=[[p('Descrição'),p('Qtd.'),p('Total')]]
    for item in doc.snapshot.get('itens',[]):linhas.append([p(item['descricao']),p(item['quantidade']),p('R$ '+item['total'])])
    util=largura-(6 if nfce else 24)*mm
    tabela=Table(linhas,colWidths=[util*.62,util*.12,util*.26],repeatRows=1)
    tabela.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.5,colors.black),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),2)]))
    partes += [tabela,Spacer(1,3*mm),p(f'Total: R$ {doc.total:.2f}'),p('Protocolo: '+(doc.protocolo or 'Ainda não autorizado')),
               p('Chave de acesso: '+(doc.chave_acesso or 'Ainda não disponível'))]
    if doc.modelo=='55' and doc.chave_acesso:
        partes.append(Code128(doc.chave_acesso,barWidth=.22*mm,barHeight=10*mm,humanReadable=False))
    if nfce and doc.qr_code:
        qr=QrCodeWidget(doc.qr_code);bounds=qr.getBounds();size=32*mm
        drawing=Drawing(size,size,transform=[size/(bounds[2]-bounds[0]),0,0,size/(bounds[3]-bounds[1]),0,0]);drawing.add(qr)
        partes += [Spacer(1,3*mm),drawing,p('Consulta: '+doc.qr_code)]
    pdf.build(partes)
    return arquivo.getvalue()
