"""Agrupamento visual: não altera campos, valores ou validações dos formulários."""
from django import forms, template

register = template.Library()

ROTULOS_FISCAIS = {
    "cnpj": "CNPJ", "razao_social": "Razão social", "ie": "Inscrição estadual", "im": "Inscrição municipal",
    "crt": "Regime tributário (CRT)", "uf": "UF", "municipio_ibge": "Código IBGE do município", "cep": "CEP",
    "modelo_mercadorias": "Modelo para mercadorias", "ativa": "Módulo fiscal ativo",
    "homologacao_validada": "Homologação validada", "producao_validada": "Produção validada",
    "csc_id": "Identificador do CSC", "qr_code_versao": "Versão do QR Code",
    "endpoints": "Endereços dos serviços", "parametros_nfse": "Parâmetros da NFS-e",
    "ncm": "NCM", "cfop": "CFOP", "cest": "CEST", "csosn": "CSOSN", "cst_icms": "CST do ICMS",
    "aliquota_icms": "Alíquota de ICMS (%)", "cst_pis": "CST do PIS", "aliquota_pis": "Alíquota de PIS (%)",
    "cst_cofins": "CST da COFINS", "aliquota_cofins": "Alíquota de COFINS (%)", "nbs": "NBS",
    "aliquota_iss": "Alíquota de ISS (%)", "iss_retido": "ISS retido",
    "item_lista_lc116": "Item da lista de serviços (LC 116)", "codigo_tributacao_nacional": "Código de tributação nacional",
    "codigo_tributacao_municipal": "Código de tributação municipal",
}

GRUPOS = {
    "ConfiguracaoForm": [
        ("Empresa e identificação fiscal", "Dados do emitente usados nos documentos desta instalação.", "cnpj razao_social nome_fantasia ie im crt"),
        ("Endereço e contato", "Localização e canais de contato da empresa.", "uf municipio_ibge municipio logradouro numero bairro cep telefone email"),
        ("Operação e ambiente", "Confira o ambiente antes de salvar. As regras de autorização existentes continuam valendo.", "ativa ambiente modelo_mercadorias natureza_operacao homologacao_validada producao_validada"),
        ("Certificado e NFC-e", "Envie um novo certificado somente quando precisar substituí-lo. Senhas vazias mantêm os dados já salvos.", "certificado_a1 senha_a1 csc_id csc qr_code_versao"),
        ("Configurações avançadas", "Ajustes do provedor e da NFS-e. Preserve a estrutura dos dados existentes.", "endpoints parametros_nfse"),
    ],
    "SolicitacaoForm": [
        ("Origem do documento", "Informe uma venda ou uma ordem de serviço. Utilize apenas uma das origens.", "venda ordem_servico"),
        ("Emissão", "Escolha o modelo e a série conforme a configuração da loja.", "modelo serie"),
        ("Destinatário", "Complemento fiscal do destinatário, quando necessário. O cadastro do cliente será preservado.", "destinatario"),
    ],
    "JustificativaForm": [("Justificativa", "Explique o motivo da solicitação com pelo menos 15 caracteres.", "justificativa")],
    "InutilizacaoForm": [
        ("Identificação da série", "Confira o modelo, a série e o ano da numeração.", "modelo serie ano"),
        ("Faixa de numeração", "Informe os limites inicial e final da faixa solicitada.", "numero_inicial numero_final"),
        ("Justificativa", "Descreva o motivo da solicitação com pelo menos 15 caracteres.", "justificativa"),
    ],
    "ProdutoForm": [
        ("Peça e classificação", "Parâmetros fiscais associados à peça, sem alterar seu cadastro comercial.", "peca ncm cfop origem unidade cest"),
        ("ICMS", "Preencha o enquadramento e a alíquota aplicáveis à operação.", "csosn cst_icms aliquota_icms"),
        ("PIS e COFINS", "Situações tributárias e alíquotas da peça.", "cst_pis aliquota_pis cst_cofins aliquota_cofins"),
        ("Tributos adicionais", "Informações complementares quando exigidas para esta operação.", "tributos_adicionais"),
    ],
    "ServicoForm": [
        ("Serviço e classificação", "Identifique o serviço e seus códigos fiscais.", "servico item_lista_lc116 codigo_tributacao_nacional codigo_tributacao_municipal nbs"),
        ("ISS e município", "Regras e local de incidência do serviço.", "aliquota_iss iss_retido municipio_incidencia"),
        ("Parâmetros adicionais", "Informações complementares do provedor municipal.", "parametros"),
    ],
    "SequenciaForm": [("Série e numeração", "A próxima numeração deve respeitar os documentos e as faixas já reservados.", "modelo ambiente serie proximo_numero")],
    "PublicacaoForm": [
        ("Dados do anúncio", "Revise os dados que serão exibidos ao comprador.", "titulo condicao preco quantidade tipo"),
        ("Envio e retirada", "Confira a modalidade de envio e os custos de frete da sua conta.", "envio retirada frete_gratis"),
        ("Descrição e fotos", "Use somente informações e imagens que podem ser publicadas no Mercado Livre.", "descricao fotos"),
    ],
}


@register.simple_tag
def organizar_formulario(form):
    usados, secoes = set(), []
    def adicionar(titulo, descricao, nomes):
        campos = []
        for nome in nomes:
            if nome not in form.fields or nome in usados or form[nome].is_hidden:
                continue
            usados.add(nome)
            bound = form[nome]
            label = ROTULOS_FISCAIS.get(nome, bound.label) if type(form).__module__ == "fiscal.forms" else bound.label
            campos.append({"field": bound, "rotulo": bound.label_tag(contents=label),
                           "largo": isinstance(bound.field.widget, (forms.Textarea, forms.CheckboxSelectMultiple))})
        if campos:
            secoes.append({"titulo": titulo, "descricao": descricao, "campos": campos})
    for titulo, descricao, nomes in GRUPOS.get(type(form).__name__, []):
        adicionar(titulo, descricao, nomes.split())
    atributos = [n for n in form.fields if n.startswith("attr_")]
    adicionar("Características da categoria", "Preencha os campos obrigatórios e complemente os demais conforme a peça. As exigências são definidas pelo Mercado Livre.", atributos)
    adicionar("Informações complementares" if secoes else "Dados do formulário", "Revise as informações antes de salvar.", form.fields)
    return secoes
