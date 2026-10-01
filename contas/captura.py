"""Sugestões para conferência. Texto de documentos nunca executa ações nem paga contas."""
import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from .boleto import processar_boleto, BoletoInvalido
from .pix import processar_pix, PixInvalido


class CapturaInvalida(ValueError):
    pass


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()


def campo(valor, origem):
    return {'valor': str(valor), 'origem': origem}


def capturar_codigo(codigo, tipo='auto', ciclo='atual'):
    codigo = str(codigo or '').strip()
    try:
        if tipo == 'pix' or (tipo == 'auto' and codigo.startswith('000201')):
            dados = processar_pix(codigo)
            campos = {'pix_copia_cola': campo(dados['pix_copia_cola'], 'PIX validado')}
            for nome in ['fornecedor', 'descricao']:
                if dados.get(nome):
                    campos[nome] = campo(dados[nome], 'Texto informado no PIX; conferir')
            titulo, forma = 'PIX Copia e Cola', 'PIX'
            avisos = dados['avisos']
        else:
            dados = processar_boleto(codigo, ciclo)
            campos = {'codigo_boleto': campo(dados['linha_digitavel'], 'Código com dígitos verificados')}
            titulo, forma = dados['tipo'], 'Boleto'
            avisos = []
            if dados.get('banco') and dados.get('vencimento'):
                avisos.append('Confira o ciclo e a data de vencimento no boleto, especialmente em documentos antigos.')
        for nome, destino in [('valor', 'valor_original'), ('vencimento', 'vencimento')]:
            if dados.get(nome) is not None:
                campos[destino] = campo(dados[nome], titulo)
            else:
                avisos.append(('Valor' if nome == 'valor' else 'Vencimento') + ' não disponível neste código; informe manualmente ou leia o documento.')
        return {'titulo': titulo, 'campos': campos, 'informacoes': dados['informacoes'],
                'avisos': avisos, 'forma': forma}
    except (BoletoInvalido, PixInvalido) as exc:
        raise CapturaInvalida(str(exc)) from exc


def capturar_texto(texto, codigos=(), ciclo='atual'):
    if not isinstance(texto, str) or len(texto) > 80000:
        raise CapturaInvalida('Documento muito extenso. Leia uma cobrança por vez (até 3 páginas).')
    if not isinstance(codigos, list) or len(codigos) > 20 or any(not isinstance(c, str) or len(c) > 4096 for c in codigos):
        raise CapturaInvalida('Quantidade ou tamanho de códigos inválido.')
    candidatos = list(codigos)
    # Não corrigir letras para números: uma alteração de OCR não pode trocar a cobrança.
    for linha in texto.splitlines():
        for trecho in re.findall(r'(?<![0-9])[0-9][0-9. \t-]{42,85}(?![0-9])', linha):
            if len(re.sub(r'\D', '', trecho)) in (44, 47, 48):
                candidatos.append(trecho.strip())
    candidatos.extend(re.findall(r'000201[^\r\n]{20,4090}?6304[0-9A-Fa-f]{4}', texto))
    opcoes, vistos, invalidos = [], set(), 0
    for codigo in candidatos[:40]:
        try:
            opcao = capturar_codigo(codigo, ciclo=ciclo)
        except CapturaInvalida:
            invalidos += 1
            continue
        chave = next(opcao['campos'][n]['valor'] for n in ['codigo_boleto', 'pix_copia_cola'] if n in opcao['campos'])
        if chave not in vistos:
            opcoes.append(opcao)
            vistos.add(chave)

    avisos = []
    if invalidos:
        avisos.append('Há códigos ilegíveis ou com dígitos inválidos. Eles não foram importados; confira o documento.')
    # Só associar rótulos ao código quando o arquivo não contém cobranças distintas.
    if len(opcoes) > 1:
        avisos.append('Mais de um código encontrado. Escolha uma cobrança; dados do texto não foram misturados entre elas.')
        return {'opcoes': opcoes, 'avisos': avisos}

    rotulos = {
        'fornecedor': r'(?:beneficiario(?: final)?|cedente|favorecido|recebedor|razao social)',
        'descricao': r'(?:descricao(?: do servico| da cobranca)?|referente a)',
        'numero_documento': r'(?:numero do documento|n[ºo°.]*(?:\s+do)?\s+documento|numero da nota(?: fiscal)?)',
        'vencimento': r'(?:data de vencimento|vencimento|pagar ate)',
        'emissao': r'(?:data de emissao|emissao|data do documento)',
        'valor_original': r'(?:valor do documento|valor original|valor total|total a pagar)',
    }
    linhas = [s.strip() for s in texto.splitlines() if s.strip()]
    encontrados = {}
    for nome, rotulo in rotulos.items():
        valores = []
        for i, linha in enumerate(linhas):
            # Rótulo ancorado evita confundir pagador com beneficiário e datas de instruções.
            match = re.match(r'^' + rotulo + r'\s*[:|\-]?\s*(.*)$', normalizar(linha))
            if not match:
                continue
            inicio = match.start(1)
            valor = linha[inicio:].strip(' :|\t')
            if not valor and i+1 < len(linhas):
                valor = linhas[i+1]
            valor = valor.split('|')[0].strip()
            if not valor or any(re.match(r'^'+r+r'\b', normalizar(valor)) for r in rotulos.values()) or re.match(r'(?i)^(pagador|sacado|cpf|cnpj|agencia|nosso numero)\b', normalizar(valor)):
                continue
            try:
                if nome in ['vencimento', 'emissao']:
                    m = re.fullmatch(r'\d{2}[/-]\d{2}[/-]\d{4}', valor)
                    if not m:
                        continue
                    valor = datetime.strptime(valor.replace('-', '/'), '%d/%m/%Y').date().isoformat()
                elif nome == 'valor_original':
                    valor = valor.replace('R$', '').strip()
                    if not re.fullmatch(r'[0-9.]+,[0-9]{2}', valor):
                        continue
                    valor = str(Decimal(valor.replace('.', '').replace(',', '.')))
                    if Decimal(valor) <= 0:
                        continue
                elif len(valor) > {'fornecedor': 160, 'descricao': 200, 'numero_documento': 100}[nome]:
                    continue
            except (ValueError, ArithmeticError):
                continue
            if valor not in valores:
                valores.append(valor)
        if len(valores) == 1:
            encontrados[nome] = campo(valores[0], 'Texto do documento / OCR — conferir')
        elif len(valores) > 1:
            avisos.append('Mais de um valor para ' + nome.replace('_', ' ') + '; preencha manualmente.')

    opcao = opcoes[0] if opcoes else {'titulo': 'Texto do documento', 'campos': {}, 'informacoes': {}, 'avisos': [], 'forma': ''}
    divergentes = {}
    for nome, sugestao in encontrados.items():
        anterior = opcao['campos'].get(nome)
        if anterior and anterior['valor'] != sugestao['valor']:
            if nome == 'valor_original' and Decimal(anterior['valor']) == Decimal(sugestao['valor']):
                continue
            divergentes[nome] = sugestao
            opcao['avisos'].append('Divergência em ' + nome.replace('_', ' ') + ': código = ' + anterior['valor'] + '; texto = ' + sugestao['valor'] + '. Confira antes de aplicar.')
        else:
            opcao['campos'][nome] = sugestao
    # Dados adicionais ficam na prévia, podendo ser preservados em observações.
    documentos = sorted(set(re.findall(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b', texto)))
    if documentos:
        opcao['informacoes']['CNPJ(s) encontrado(s), conferir titular'] = ', '.join(documentos[:8])
    for nome in divergentes:
        # Nunca escolher silenciosamente entre valores divergentes.
        opcao['campos'].pop(nome, None)
    if opcao['campos'] or opcao['informacoes']:
        opcoes = [opcao]
    if not opcoes:
        avisos.append('Nenhum dado identificado com segurança. Use uma foto nítida ou preencha os campos manualmente.')
    return {'opcoes': opcoes, 'avisos': avisos}
