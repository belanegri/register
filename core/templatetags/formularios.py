"""Agrupamento visual: não altera campos, valores ou validações dos formulários."""
from django import forms, template

register = template.Library()

ROTULOS_FISCAIS = {
    "cnpj": "CNPJ", "razao_social": "Razão social", "ie": "Inscrição estadual", "im": "Inscrição municipal",
    "crt": "Regime tributário (CRT)", "uf": "UF", "municipio_ibge": "Código IBGE do município", "cep": "CEP",
    "serie_padrao": "Série padrão da NF-e", "modelo_mercadorias": "Modelo para mercadorias", "ativa": "Módulo fiscal ativo",
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
    "EtiquetaEntregaForm": [
        ("Remetente", "Dados da empresa que envia a mercadoria. Confira antes de imprimir.", "remetente_nome remetente_documento remetente_telefone remetente_endereco"),
        ("Destinatário", "Selecione um cliente para carregar os dados ou preencha manualmente.", "cliente destinatario_nome destinatario_documento destinatario_telefone destinatario_endereco"),
        ("Informações da entrega", "Identifique o pedido, o volume e os cuidados necessários.", "referencia volume observacoes"),
    ],
    "ConfiguracaoForm": [
        ("Empresa e identificação fiscal", "Dados do emitente usados nos documentos desta instalação.", "cnpj razao_social nome_fantasia ie im crt"),
        ("Endereço e contato", "Localização e canais de contato da empresa.", "cep logradouro numero complemento bairro municipio uf municipio_ibge telefone email"),
        ("Operação e ambiente", "Confira o ambiente antes de salvar. As regras de autorização existentes continuam valendo.", "ativa ambiente modelo_mercadorias serie_padrao natureza_operacao exigir_classificacao_individual homologacao_validada producao_validada"),
        ("Certificado e NFC-e", "Envie um novo certificado somente quando precisar substituí-lo. Senhas vazias mantêm os dados já salvos.", "certificado_a1 senha_a1 csc_id csc qr_code_versao"),
        ("Configurações avançadas", "Ajustes do provedor e da NFS-e. Preserve a estrutura dos dados existentes.", "endpoints parametros_nfse"),
    ],
    "ImportacaoCompraForm": [
        ("XML do fornecedor", "Selecione o arquivo original da NF-e recebida na compra.", "arquivo"),
    ],
    "EntradaForm": [
        ("Operação de entrada", "Confira a referência, a natureza e o CFOP desta compra.", "referencia serie natureza_operacao cfop"),
        ("Fornecedor", "Pessoa ou empresa de quem a mercadoria foi adquirida.", "fornecedor_cadastro fornecedor_nome fornecedor_documento fornecedor_ind_ie fornecedor_ie"),
        ("Endereço do fornecedor", "Endereço fiscal usado na NF-e de entrada.", "cep logradouro numero complemento bairro municipio uf municipio_ibge"),
        ("Transporte e frete", "Informe quem contrata o transporte e somente o valor do frete. Os dados serão conferidos antes de emitir.", "transporte_modalidade valor_frete"),
        ("Transportador", "Preencha os dados da transportadora ou do responsável pelo envio, quando houver.", "transportadora_cadastro transporte_nome transporte_documento transporte_ie transporte_endereco transporte_municipio transporte_uf"),
        ("Veículo e volumes", "Identifique os volumes e os pesos em kg. Veículo e ANTT podem ficar vazios quando não se aplicarem.", "transporte_placa transporte_uf_veiculo transporte_rntc transporte_volumes transporte_especie transporte_marca transporte_numeracao transporte_peso_liquido transporte_peso_bruto"),
    ],
    "SolicitacaoForm": [
        ("Origem da nota", "Selecione a venda ou a OS concluída. Os itens e valores são carregados para conferência.", "venda ordem_servico modelo serie"),
        ("Cliente e enquadramento", "Confira quem recebe a mercadoria e a condição do destinatário.", "cliente_cadastro destinatario_nome destinatario_documento destinatario_ind_ie destinatario_ie consumidor_final"),
        ("Endereço fiscal do cliente", "Confira o endereço usado na NF-e.", "destinatario_cep destinatario_logradouro destinatario_numero destinatario_complemento destinatario_bairro destinatario_municipio destinatario_uf destinatario_municipio_ibge"),
        ("Transporte e frete", "Informe quem contrata o transporte e somente o valor do frete. Os dados serão conferidos antes de emitir.", "transporte_modalidade valor_frete"),
        ("Transportador", "Preencha os dados da transportadora ou do responsável pelo envio, quando houver.", "transportadora_cadastro transporte_nome transporte_documento transporte_ie transporte_endereco transporte_municipio transporte_uf"),
        ("Veículo e volumes", "Identifique os volumes e os pesos em kg. Veículo e ANTT podem ficar vazios quando não se aplicarem.", "transporte_placa transporte_uf_veiculo transporte_rntc transporte_volumes transporte_especie transporte_marca transporte_numeracao transporte_peso_liquido transporte_peso_bruto"),
        ("Tributos da operação", "Confira o CFOP e a alíquota correspondentes a esta operação.", "natureza_operacao cfop aliquota_icms"),
        ("DIFAL · consumidor final em outro estado", "Preencha somente para não contribuinte em outra UF, com parâmetros confirmados pela contabilidade.", "difal_aliquota_interna difal_aliquota_fcp difal_base_integral_preco_final"),
    ],
    "TransporteForm": [
        ("Transporte e frete", "Informe quem contrata o transporte e somente o valor do frete. Os dados serão conferidos antes de emitir.", "transporte_modalidade valor_frete"),
        ("Transportador", "Preencha os dados da transportadora ou do responsável pelo envio, quando houver.", "transportadora_cadastro transporte_nome transporte_documento transporte_ie transporte_endereco transporte_municipio transporte_uf"),
        ("Veículo e volumes", "Identifique os volumes e os pesos em kg. Veículo e ANTT podem ficar vazios quando não se aplicarem.", "transporte_placa transporte_uf_veiculo transporte_rntc transporte_volumes transporte_especie transporte_marca transporte_numeracao transporte_peso_liquido transporte_peso_bruto"),
    ],
    "JustificativaForm": [("Justificativa", "Explique o motivo da solicitação com pelo menos 15 caracteres.", "justificativa")],
    "InutilizacaoForm": [
        ("Identificação da série", "Confira o modelo, a série e o ano da numeração.", "modelo serie ano"),
        ("Faixa de numeração", "Informe os limites inicial e final da faixa solicitada.", "numero_inicial numero_final"),
        ("Justificativa", "Descreva o motivo da solicitação com pelo menos 15 caracteres.", "justificativa"),
    ],
    "ProdutoPadraoForm": [
        ("Classificação padrão das peças", "Usada nas peças atuais e futuras que não tenham uma exceção individual.", "natureza_operacao ncm cfop cfop_interestadual_contribuinte cfop_interestadual_nao_contribuinte origem unidade cest"),
        ("ICMS", "Preencha o enquadramento e a alíquota aplicáveis à operação.", "csosn cst_icms aliquota_icms"),
        ("PIS e COFINS", "Situações tributárias e alíquotas padrão.", "cst_pis aliquota_pis cst_cofins aliquota_cofins base_pis_cofins"),
        ("IBS e CBS", "Tributação integral conforme o enquadramento e o ano da emissão.", "ibscbs_ativo cst_ibscbs cclass_trib aliquota_ibs_uf aliquota_ibs_municipal aliquota_cbs"),
        ("Tributos adicionais", "Informações complementares quando exigidas para esta operação.", "tributos_adicionais"),
    ],
    "ProdutoForm": [
        ("Peça e classificação", "Parâmetros fiscais associados à peça, sem alterar seu cadastro comercial.", "peca natureza_operacao ncm cfop cfop_interestadual_contribuinte cfop_interestadual_nao_contribuinte origem unidade cest classificacao_conferida"),
        ("ICMS", "Preencha o enquadramento e a alíquota aplicáveis à operação.", "csosn cst_icms aliquota_icms"),
        ("PIS e COFINS", "Situações tributárias e alíquotas da peça.", "cst_pis aliquota_pis cst_cofins aliquota_cofins base_pis_cofins"),
        ("Tributos adicionais", "Informações complementares quando exigidas para esta operação.", "tributos_adicionais"),
    ],
    "ServicoForm": [
        ("Serviço e classificação", "Identifique o serviço e seus códigos fiscais.", "servico item_lista_lc116 codigo_tributacao_nacional codigo_tributacao_municipal nbs"),
        ("ISS e município", "Regras e local de incidência do serviço.", "aliquota_iss iss_retido municipio_incidencia"),
        ("Parâmetros adicionais", "Informações complementares do provedor municipal.", "parametros"),
    ],
    "SequenciaForm": [("Série e numeração", "A próxima numeração deve respeitar os documentos e as faixas já reservados.", "modelo ambiente serie proximo_numero")],
    "PublicacaoForm": [
        ("Dados do anúncio", "Revise os dados que serão exibidos ao comprador.", "titulo sku condicao preco quantidade tipo"),
        ("Garantia", "Confira o tipo e o prazo da garantia que constarão no anúncio.", "garantia_tipo garantia_prazo garantia_unidade"),
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
            recolhivel=type(form).__name__ in ('SolicitacaoForm','EntradaForm','TransporteForm') and titulo in ('Transportador','Veículo e volumes')
            aberta=any(item['field'].errors or item['field'].value() not in (None,'') for item in campos)
            secoes.append({"titulo": titulo, "descricao": descricao, "campos": campos,"recolhivel":recolhivel,"aberta":aberta})
    for titulo, descricao, nomes in GRUPOS.get(type(form).__name__, []):
        adicionar(titulo, descricao, nomes.split())
    adicionar("Observação final da nota", "Texto adicional que será impresso nas informações complementares.", ["observacao_final"])
    atributos = [n for n in form.fields if n.startswith("attr_")]
    if hasattr(form, "atributos"):
        principais = [chave for atributo, chave in form.atributos if form.fields[chave].required]
        regulatorios = [chave for atributo, chave in form.atributos if atributo["id"] == "INMETRO_CERTIFICATION_REGISTRATION_NUMBER"]
        secundarios = [chave for chave in atributos if chave not in principais and chave not in regulatorios]
        adicionar("Características principais", "Preencha os dados obrigatórios da categoria.", principais)
        adicionar("Características secundárias", "Complete as informações aplicáveis à peça ou marque Não se aplica.", secundarios)
        adicionar("Informação regulatória", "Informe o registro ou certificação da peça quando aplicável.", regulatorios)
    else:
        adicionar("Características da categoria", "Preencha as características aplicáveis à peça.", atributos)
    adicionar("Informações complementares" if secoes else "Dados do formulário", "Revise as informações antes de salvar.", form.fields)
    return secoes
