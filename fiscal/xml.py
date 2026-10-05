"""Leiautes oficiais. O XSD instalado é obrigatório antes de transmitir."""
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from lxml import etree

from .seguranca import ErroFiscal, assinatura_xml, descriptografar, validar_url, xml_seguro

NFE = 'http://www.portalfiscal.inf.br/nfe'
NFSE = 'http://www.sped.fazenda.gov.br/nfse'
UFS = dict(zip('RO AC AM RR PA AP TO MA PI CE RN PB PE AL SE BA MG ES RJ SP PR SC RS MS MT GO DF'.split(),
               '11 12 13 14 15 16 17 21 22 23 24 25 26 27 28 29 31 32 33 35 41 42 43 50 51 52 53'.split()))


def valor(v):
    return str(Decimal(v).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def el(pai, nome, texto=None, **atributos):
    ns = etree.QName(pai).namespace
    filho = etree.SubElement(pai, f'{{{ns}}}{nome}', **atributos)
    if texto is not None:
        filho.text = str(texto)
    return filho


def campos(pai, dados):
    for nome, texto in dados.items():
        el(pai, nome, texto)


def grupos(pai, dados):
    """Extensões tributárias explícitas do leiaute; sem XML concatenado."""
    if not isinstance(dados, dict):
        raise ErroFiscal('Parâmetros tributários adicionais inválidos.')
    for nome, conteudo in dados.items():
        if not nome.isidentifier() or nome.lower() in ('signature', 'xml'):
            raise ErroFiscal('Nome de grupo tributário inválido.')
        filho = el(pai, nome)
        if isinstance(conteudo, dict):
            grupos(filho, conteudo)
        elif isinstance(conteudo, (str, int, float)):
            filho.text = str(conteudo)
        else:
            raise ErroFiscal('Valor tributário inválido.')


def validar_schema(raiz, arquivo, pasta='nfe'):
    base = Path(settings.FISCAL_SCHEMA_DIR).resolve()
    caminho = (base / pasta / arquivo).resolve()
    if not caminho.is_relative_to(base) or not caminho.is_file():
        raise ErroFiscal(f'Instale o esquema oficial {pasta}/{arquivo} antes de transmitir.')
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        if pasta=='nfse':
            class CompatibilidadeSerie(etree.Resolver):
                def resolve(self, url, public_id, context):
                    # O pacote oficial 1.01 usa âncoras de regex .NET nesta única
                    # expressão. Em XSD/libxml2 ^/$ são literais: adaptar somente
                    # a expressão, preservando os limites e o arquivo original.
                    if str(url).endswith('tiposSimples_v1.01.xsd'):
                        alvo=caminho.parent/'tiposSimples_v1.01.xsd'
                        dados=alvo.read_bytes().replace(b'value="^0{0,4}\\d{1,5}$"',b'value="0{0,4}\\d{1,5}"')
                        return self.resolve_string(dados,context,base_url=str(alvo))
                    return None
            parser.resolvers.add(CompatibilidadeSerie())
        schema = etree.XMLSchema(etree.parse(str(caminho), parser))
        schema.assertValid(raiz)
    except (etree.XMLSyntaxError, etree.XMLSchemaError, etree.DocumentInvalid):
        raise ErroFiscal('XML não atende ao esquema oficial. Revise os parâmetros fiscais e a versão do leiaute.') from None


def chave_nfe(doc):
    e = doc.snapshot['empresa']
    if e['uf'] not in UFS:
        raise ErroFiscal('UF fiscal inválida.')
    cnf = str(int(doc.idempotencia.hex[:8], 16) % 100000000).zfill(8)
    data = timezone.localtime(doc.emitido_em).strftime('%y%m')
    base = UFS[e['uf']] + data + e['cnpj'] + doc.modelo + str(doc.serie).zfill(3) + str(doc.numero).zfill(9) + doc.tipo_emissao + cnf
    if len(base) != 43 or not base.isdigit():
        raise ErroFiscal('Identificação fiscal inválida para a chave de acesso.')
    soma = sum(int(n) * (2 + i % 8) for i, n in enumerate(reversed(base)))
    resto = soma % 11
    return base + str(0 if resto in (0, 1) else 11-resto)


def gerar_nfe(doc, config):
    e = doc.snapshot['empresa']; itens = doc.snapshot['itens']
    chave = doc.chave_acesso or chave_nfe(doc)
    raiz = etree.Element(f'{{{NFE}}}NFe', nsmap={None: NFE})
    inf = el(raiz, 'infNFe', Id='NFe'+chave, versao='4.00')
    ide = el(inf, 'ide')
    campos(ide, {'cUF': UFS[e['uf']], 'cNF': chave[35:43], 'natOp': e['natureza_operacao'],
        'mod': doc.modelo, 'serie': doc.serie, 'nNF': doc.numero,
        'dhEmi': timezone.localtime(doc.emitido_em).isoformat(timespec='seconds'),
        'tpNF': '1', 'idDest': doc.snapshot.get('id_destino', '1'), 'cMunFG': e['municipio_ibge'],
        'tpImp': '4' if doc.modelo == '65' else '1', 'tpEmis': doc.tipo_emissao, 'cDV': chave[-1],
        'tpAmb': '2' if doc.ambiente == 'homologacao' else '1', 'finNFe': '1',
        'indFinal': '1', 'indPres': '1', 'procEmi': '0', 'verProc': 'REGISTER-fiscal-1'})
    if doc.tipo_emissao=='9':
        campos(ide,{'dhCont':timezone.localtime(doc.emitido_em).isoformat(timespec='seconds'),
                    'xJust':doc.snapshot.get('contingencia_justificativa','Indisponibilidade do servico autorizador')})
    emit = el(inf, 'emit')
    campos(emit, {'CNPJ': e['cnpj'], 'xNome': e['razao_social']})
    end = el(emit, 'enderEmit')
    campos(end, {'xLgr': e['logradouro'], 'nro': e['numero'], 'xBairro': e['bairro'],
        'cMun': e['municipio_ibge'], 'xMun': e['municipio'], 'UF': e['uf'], 'CEP': e['cep'],
        'cPais': '1058', 'xPais': 'BRASIL'})
    campos(emit, {'IE': e['ie'], 'CRT': e['crt']})
    dest = doc.snapshot.get('destinatario', {})
    if doc.modelo == '55' and not dest.get('documento'):
        raise ErroFiscal('Informe CPF/CNPJ e endereço fiscal estruturado do destinatário para NF-e.')
    if dest.get('documento'):
        if len(dest['documento']) not in (11, 14) or not dest['documento'].isdigit():
            raise ErroFiscal('CPF/CNPJ do destinatário inválido.')
        d = el(inf, 'dest')
        campos(d, {'CNPJ' if len(dest['documento']) == 14 else 'CPF': dest['documento'],
                   'xNome': 'NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL' if doc.ambiente == 'homologacao' else dest['nome']})
        if doc.modelo == '55':
            obrigatorios = ('logradouro', 'numero', 'bairro', 'municipio_ibge', 'municipio', 'uf', 'cep')
            if not all(dest.get(k) for k in obrigatorios):
                raise ErroFiscal('Preencha o endereço fiscal estruturado do destinatário.')
            campos(el(d, 'enderDest'), dict(zip(('xLgr','nro','xBairro','cMun','xMun','UF','CEP'), [dest[k] for k in obrigatorios])))
        campos(d, {'indIEDest': dest.get('ind_ie', '9')})
        if dest.get('ie'):
            el(d, 'IE', dest['ie'])
    totais = {k: Decimal('0') for k in ('vBC', 'vICMS', 'vPIS', 'vCOFINS', 'vProd', 'vDesc')}
    for i, item in enumerate(itens, 1):
        t = item['fiscal']; total = Decimal(item['total']); bruto = Decimal(item['bruto'])
        det = el(inf, 'det', nItem=str(i)); prod = el(det, 'prod')
        campos(prod, {'cProd': item['codigo'], 'cEAN': 'SEM GTIN',
            'xProd': 'NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL' if doc.modelo == '65' and doc.ambiente == 'homologacao' and i == 1 else item['descricao'],
            'NCM': t['ncm'], 'CFOP': t['cfop'], 'uCom': t['unidade'], 'qCom': item['quantidade'],
            'vUnCom': item['preco_unitario'], 'vProd': valor(bruto), 'cEANTrib': 'SEM GTIN',
            'uTrib': t['unidade'], 'qTrib': item['quantidade'], 'vUnTrib': item['preco_unitario']})
        if Decimal(item['desconto']):
            el(prod, 'vDesc', item['desconto'])
        el(prod, 'indTot', '1')
        imposto = el(det, 'imposto'); icms = el(imposto, 'ICMS')
        if e['crt'] in ('1', '4'):
            if t['csosn'] not in ('102', '103', '300', '400'):
                raise ErroFiscal('CSOSN exige tratamento específico ainda não configurado neste leiaute.')
            campos(el(icms, 'ICMSSN102'), {'orig': t['origem'], 'CSOSN': t['csosn']})
        elif t['cst_icms'] == '00':
            calculado = Decimal(valor(total*Decimal(t['aliquota_icms'])/100))
            campos(el(icms, 'ICMS00'), {'orig': t['origem'], 'CST': '00', 'modBC': '3', 'vBC': valor(total), 'pICMS': t['aliquota_icms'], 'vICMS': valor(calculado)})
            totais['vBC'] += total; totais['vICMS'] += calculado
        else:
            raise ErroFiscal('CST ICMS exige tratamento específico. Não será aplicado imposto por aproximação.')
        for nome, campo_cst, campo_aliq, campo_total in [('PIS','cst_pis','aliquota_pis','vPIS'), ('COFINS','cst_cofins','aliquota_cofins','vCOFINS')]:
            grupo = el(imposto, nome); cst = t[campo_cst]
            if cst in ('01', '02'):
                imposto_valor = Decimal(valor(total*Decimal(t[campo_aliq])/100)); totais[campo_total] += imposto_valor
                campos(el(grupo,nome+'Aliq'), {'CST':cst, 'vBC':valor(total), 'p'+nome:t[campo_aliq], 'v'+nome:valor(imposto_valor)})
            elif cst in ('04','05','06','07','08','09'):
                campos(el(grupo,nome+'NT'), {'CST':cst})
            else:
                raise ErroFiscal(f'CST {nome} exige parametrização específica.')
        grupos(imposto, t.get('tributos_adicionais', {}))
        totais['vProd'] += bruto; totais['vDesc'] += Decimal(item['desconto'])
    total = el(inf, 'total'); icmstot = el(total, 'ICMSTot')
    for k in ('vBC','vICMS','vICMSDeson','vFCP','vBCST','vST','vFCPST','vFCPSTRet','vProd','vFrete','vSeg','vDesc','vII','vIPI','vIPIDevol','vPIS','vCOFINS','vOutro'):
        el(icmstot, k, valor(totais.get(k, 0)))
    el(icmstot, 'vNF', valor(doc.total))
    campos(el(inf, 'transp'), {'modFrete': '9'})
    pagamento = el(inf, 'pag'); campos(el(pagamento, 'detPag'), {'tPag': doc.snapshot.get('tipo_pagamento','99'), 'xPag':'Outros', 'vPag':valor(doc.total)})
    # infNFeSupl será inserido antes de Signature, na ordem do XSD.
    assinatura_xml(raiz, 'infNFe', config)
    if doc.modelo == '65':
        base_url = config.endpoints.get(doc.ambiente, {}).get('65', {}).get('qr_code')
        consulta = config.endpoints.get(doc.ambiente, {}).get('65', {}).get('consulta_publica')
        if not base_url or not consulta:
            raise ErroFiscal('Configure as URLs oficiais do QR Code e consulta pública da NFC-e.')
        validar_url(base_url, doc.ambiente); validar_url(consulta, doc.ambiente)
        ambiente='2' if doc.ambiente=='homologacao' else '1'
        if config.qr_code_versao=='3':
            dados=f'{chave}|3|{ambiente}'
            if doc.tipo_emissao=='9':
                from .seguranca import material_a1
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import padding
                import base64
                documento=dest.get('documento','')
                tipo='1' if len(documento)==14 else '2' if len(documento)==11 else ''
                dados+=f"|{timezone.localtime(doc.emitido_em).day:02d}|{valor(doc.total)}|{tipo}|{documento}"
                chave_privada,_,_=material_a1(config)
                assinatura=base64.b64encode(chave_privada.sign(dados.encode(),padding.PKCS1v15(),hashes.SHA1())).decode()
                dados+='|'+assinatura
        else:
            if doc.tipo_emissao!='1':raise ErroFiscal('Use QR Code 3.00 para contingência neste adaptador.')
            if not config.csc_id or not config.csc_criptografado or config.csc_ambiente!=doc.ambiente:
                raise ErroFiscal('Configure o CSC da NFC-e neste ambiente.')
            dados=f'{chave}|2|{ambiente}|{int(config.csc_id)}'
            hash_qr=hashlib.sha1((dados+descriptografar(config.csc_criptografado).decode()).encode()).hexdigest().upper()
            dados+='|'+hash_qr
        qr=base_url+('&' if '?' in base_url else '?')+'p='+dados
        supl = etree.Element(f'{{{NFE}}}infNFeSupl'); campos(supl, {'qrCode':qr, 'urlChave':consulta})
        raiz.insert(1, supl)
    else:
        qr = ''
    validar_schema(raiz, 'nfe_v4.00.xsd')
    return etree.tostring(raiz, encoding='unicode'), chave, qr


def gerar_dps(doc, config):
    e = doc.snapshot['empresa']; itens = doc.snapshot['itens']; t = itens[0]['fiscal']
    if any(i['fiscal'] != t for i in itens):
        raise ErroFiscal('A DPS deve reunir serviços com os mesmos parâmetros fiscais. Separe as operações fiscais.')
    parametros = config.parametros_nfse
    if not parametros.get('municipio_conveniado'):
        raise ErroFiscal('Valide a adesão e os parâmetros do município no Emissor Nacional NFS-e.')
    identificador = f"DPS{e['municipio_ibge']}2{e['cnpj']}{doc.serie:05d}{doc.numero:015d}"
    raiz = etree.Element(f'{{{NFSE}}}DPS', nsmap={None: NFSE}, versao='1.01')
    inf = el(raiz, 'infDPS', Id=identificador)
    campos(inf, {'tpAmb': '2' if doc.ambiente == 'homologacao' else '1',
        'dhEmi': timezone.localtime(doc.emitido_em).isoformat(timespec='seconds'), 'verAplic':'REGISTER-fiscal-1',
        'serie': doc.serie, 'nDPS': doc.numero, 'dCompet':timezone.localtime(doc.emitido_em).date().isoformat(),
        'tpEmit':'1', 'cLocEmi':e['municipio_ibge']})
    prest = el(inf, 'prest'); el(prest, 'CNPJ',e['cnpj'])
    if e['im']: el(prest,'IM',e['im'])
    regime=el(prest,'regTrib');op=parametros.get('opSimpNac','2' if e['crt']=='4' else '3' if e['crt'] in ('1','2') else '1')
    el(regime,'opSimpNac',op)
    if op=='3':el(regime,'regApTribSN',parametros.get('regApTribSN','1'))
    el(regime,'regEspTrib',parametros.get('regEspTrib','0'))
    dest = doc.snapshot.get('destinatario', {})
    if dest.get('documento'):
        toma=el(inf,'toma'); campos(toma, {'CNPJ' if len(dest['documento'])==14 else 'CPF':dest['documento'], 'xNome':dest['nome']})
    serv=el(inf,'serv');campos(el(serv,'locPrest'), {'cLocPrestacao':t['municipio_incidencia']})
    codigo=el(serv,'cServ');el(codigo,'cTribNac',t['codigo_tributacao_nacional'])
    if t['codigo_tributacao_municipal']:el(codigo,'cTribMun',t['codigo_tributacao_municipal'])
    el(codigo,'xDescServ','; '.join(i['descricao'] for i in itens)[:1000])
    if t['nbs']:el(codigo,'cNBS',t['nbs'])
    valores=el(inf,'valores');campos(el(valores,'vServPrest'), {'vServ':valor(doc.total)})
    trib=el(valores,'trib'); municipal=el(trib,'tribMun');campos(municipal, {'tribISSQN':'1', 'tpRetISSQN':'2' if t['iss_retido'] else '1'})
    if Decimal(t['aliquota_iss']):el(municipal,'pAliq',valor(t['aliquota_iss']))
    campos(el(trib,'totTrib'), {'indTotTrib':'0'})
    grupos(inf, t.get('parametros', {}))
    assinatura_xml(raiz,'infDPS',config,sha256=True)
    validar_schema(raiz,'DPS_v1.01.xsd','nfse')
    return etree.tostring(raiz,encoding='unicode'), identificador, ''


def gerar_documento(doc, config):
    return gerar_dps(doc, config) if doc.modelo == 'nfse' else gerar_nfe(doc, config)
