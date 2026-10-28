from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as ImagemPDF
from reportlab.graphics.barcode.code128 import Code128
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing


def gerar_danfe_nfe(doc):
    from brazilfiscalreport.danfe import Danfe, DanfeConfig
    from .seguranca import ErroFiscal, xml_seguro
    from .models import Status
    autorizado = doc.status in (Status.AUTORIZADA, Status.CANCELADA)
    xml = doc.xml_autorizado if autorizado else doc.xml_assinado
    if not xml:
        raise ErroFiscal('O XML desta NF-e ainda não está disponível para gerar o DANFE.')
    raiz = xml_seguro(xml)
    inf = raiz.find('.//{*}infNFe')
    if inf is None or inf.get('Id') != 'NFe' + doc.chave_acesso:
        raise ErroFiscal('O XML não corresponde à chave desta NF-e.')
    amb = inf.findtext('.//{*}tpAmb')
    if amb != ('1' if doc.ambiente == 'producao' else '2'):
        raise ErroFiscal('O ambiente do XML difere desta NF-e.')
    if autorizado:
        prot = raiz.find('.//{*}infProt')
        if (prot is None or prot.findtext('{*}cStat') not in ('100', '150')
                or not doc.protocolo or prot.findtext('{*}nProt') != doc.protocolo
                or prot.findtext('{*}chNFe') != doc.chave_acesso):
            raise ErroFiscal('O protocolo de autorização não corresponde a esta NF-e.')
    from .logos import logo_empresa
    config = DanfeConfig(logo=logo_empresa(), watermark_cancelled=doc.status == Status.CANCELADA)
    return bytes(Danfe(xml=xml, config=config).output())


def gerar_auxiliar(doc):
    if doc.modelo == '55' and (doc.status in ('autorizada', 'cancelada') or doc.xml_assinado or doc.xml_autorizado):
        return gerar_danfe_nfe(doc)
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
        p(f'{doc.get_modelo_display()} · Série {doc.serie} · Nº {doc.numero}'),p(doc.get_status_display()),p('Operação: '+doc.get_operacao_display())]
    from .logos import logo_empresa
    logo=logo_empresa()
    if logo:
        from reportlab.lib.utils import ImageReader
        w,h=ImageReader(logo).getSize()
        escala=min((35 if nfce else 45)*mm/w,20*mm/h)
        imagem=ImagemPDF(logo,width=w*escala,height=h*escala);imagem.hAlign='CENTER'
        partes=[imagem,Spacer(1,2*mm)]+partes
    if doc.numero_nfse:partes.append(p('Número da NFS-e autorizada: '+doc.numero_nfse))
    if doc.ambiente=='homologacao' or doc.status!='autorizada':
        partes += [Paragraph('SEM VALOR FISCAL — HOMOLOGAÇÃO OU DOCUMENTO NÃO AUTORIZADO',titulo)]
    partes += [p('Emissão: '+doc.emitido_em.strftime('%d/%m/%Y %H:%M')),p('Natureza: '+empresa.get('natureza_operacao',''))]
    partes += [p(('Fornecedor: ' if doc.operacao=='0' else 'Destinatário: ')+doc.snapshot.get('destinatario',{}).get('nome','Consumidor')),Spacer(1,3*mm)]
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
    if doc.snapshot.get('observacao_final'):
        partes += [Spacer(1,3*mm),Paragraph('Informações complementares',titulo),p(doc.snapshot['observacao_final'])]
    pdf.build(partes)
    return arquivo.getvalue()
