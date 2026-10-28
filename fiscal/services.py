"""Transações exclusivamente fiscais; nenhuma escrita no fluxo comercial."""
import hashlib
import re
from decimal import Decimal, ROUND_DOWN

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (Ambiente, Modelo, Status, ConfiguracaoFiscal, DocumentoFiscal,
                     EventoFiscal, ParametroProduto, ParametroServico, SequenciaFiscal, TentativaTransmissao, Operacao)
from .provedores import provedor
from .seguranca import ErroFiscal, resposta_sanitizada
from .xml import gerar_documento, chave_nfe, valor
from .operacoes import validar_cfop, dados_fiscais, parametro_para_nota, cfop_saida


def exigir(usuario, permissao):
    if not usuario.is_authenticated or not usuario.has_perm('fiscal.'+permissao):
        raise PermissionDenied


def habilitado(config, ambiente=None):
    if not settings.FISCAL_ENABLED or not config.ativa:
        raise ErroFiscal('O módulo fiscal está desativado nesta instalação.')
    ambiente = ambiente or config.ambiente
    if ambiente == Ambiente.PRODUCAO and not (settings.FISCAL_ALLOW_PRODUCTION and config.homologacao_validada and config.producao_validada):
        raise ErroFiscal('Emissão em produção bloqueada. Valide a homologação e libere explicitamente esta instalação.')


def _snapshot(config, origem, itens, modelo, destinatario, cfop=None, natureza_operacao=None, aliquota_icms=None, ind_final='1', valor_frete=0, difal=None, transporte=None, observacao_final=''):
    from django.forms.models import model_to_dict
    if ind_final not in ('0','1'):raise ErroFiscal('Indicador de consumidor final inválido.')
    empresa = {k: getattr(config,k) for k in ('cnpj','razao_social','nome_fantasia','ie','im','crt','uf',
        'municipio_ibge','municipio','logradouro','numero','complemento','bairro','cep','natureza_operacao')}
    cliente = origem.cliente
    dados_dest = cliente.dados_fiscais() if cliente else {'nome':getattr(origem,'cliente_nome',''),'documento':''}
    dados_dest.update(destinatario or {})
    selecionados = [i for i in itens if bool(i.servico_id) == (modelo == Modelo.NFSE)]
    if not selecionados:
        raise ErroFiscal('A origem não possui itens do tipo fiscal selecionado.')
    total_bruto = sum((Decimal(i.quantidade)*Decimal(getattr(i,'preco_unitario',getattr(i,'preco',0))) for i in itens),Decimal('0'))
    # Venda já tem rateio persistido. OS ainda sem venda usa rateio proporcional em centavos.
    rateios = None
    if not hasattr(origem,'subtotal'):
        desconto = Decimal(origem.desconto)
        if desconto<0 or desconto>=total_bruto:
            raise ErroFiscal('Os valores da OS não permitem solicitar o documento fiscal.')
        quotas = [desconto*Decimal(i.quantidade)*Decimal(i.preco)/total_bruto for i in itens]
        rateios = [q.quantize(Decimal('.01'),rounding=ROUND_DOWN) for q in quotas]
        restos = sorted(range(len(itens)),key=lambda i:quotas[i]-rateios[i],reverse=True)
        for n in restos[:int((desconto-sum(rateios))*100)]:rateios[n]+=Decimal('.01')
    linhas=[]; naturezas=set(); destinos=set()
    for i in selecionados:
        try:
            params = (ParametroServico.objects.get(servico_id=i.servico_id) if modelo==Modelo.NFSE
                      else parametro_para_nota(config,i.peca_id))
        except (ParametroProduto.DoesNotExist,ParametroServico.DoesNotExist):
            raise ErroFiscal('Cadastre os parâmetros fiscais de todos os itens selecionados.') from None
        fiscal=dados_fiscais(params)
        if modelo != Modelo.NFSE:
            fiscal['cfop']=cfop_saida(params,config,dados_dest,cfop)
            if fiscal['cfop'].startswith('6') and (params.cfop_interestadual_contribuinte or params.cfop_interestadual_nao_contribuinte) and aliquota_icms is None:
                raise ErroFiscal('Informe a alíquota interestadual de ICMS confirmada pela contabilidade para esta nota.')
            if aliquota_icms is not None:fiscal['aliquota_icms']=str(aliquota_icms)
            destinos.add({'5':'1','6':'2','7':'3'}[fiscal['cfop'][0]])
            if params.natureza_operacao:naturezas.add(params.natureza_operacao)
        preco=Decimal(getattr(i,'preco_unitario',getattr(i,'preco',0)))
        bruto=preco*i.quantidade
        desconto=Decimal(i.desconto) if rateios is None else rateios[itens.index(i)]
        total=bruto-desconto
        linhas.append({'origem_item':i.pk,'codigo':str(i.servico.codigo if i.servico_id else i.peca.codigo),
            'descricao':i.descricao,'quantidade':i.quantidade,'preco_unitario':str(preco),
            'bruto':valor(bruto),'desconto':valor(desconto),'total':valor(total),'fiscal':fiscal})
    if natureza_operacao:empresa['natureza_operacao']=natureza_operacao
    elif len(naturezas)==1:empresa['natureza_operacao']=next(iter(naturezas))
    if len(destinos)>1:raise ErroFiscal('Os CFOPs devem corresponder ao mesmo destino da operação.')
    destino=next(iter(destinos),'1')
    if destino=='3':raise ErroFiscal('Exportação exige informações específicas ainda não disponíveis neste formulário.')
    if modelo!='nfse' and dados_dest.get('uf') and destino!=('1' if dados_dest['uf']==config.uf else '2'):
        raise ErroFiscal('CFOP incompatível com a UF do destinatário.')
    from .frete import aplicar_frete
    total=aplicar_frete(linhas,valor_frete,modelo)
    snapshot={'empresa':empresa,'destinatario':dados_dest,'itens':linhas,'origem_codigo':origem.codigo,'valor_frete':valor(valor_frete or 0),
        'id_destino':destino,'ind_final':ind_final,'cfop_nota':cfop or '', 'aliquota_icms_nota':str(aliquota_icms) if aliquota_icms is not None else None, 'natureza_personalizada':bool(natureza_operacao)}
    from .difal import configurar_difal
    configurar_difal(snapshot,modelo,difal)
    from .transporte import normalizar_transporte
    snapshot['transporte']=normalizar_transporte(transporte,frete=valor_frete,modelo=modelo)
    from .observacoes import normalizar_observacao
    snapshot['observacao_final']=normalizar_observacao(observacao_final,modelo)
    return snapshot,total


@transaction.atomic
def solicitar(usuario, *, venda_id=None, os_id=None, modelo=None, serie=None, destinatario=None, operacao=Operacao.SAIDA, cfop=None, natureza_operacao=None, aliquota_icms=None,ind_final='1',valor_frete=0,difal=None,transporte=None,observacao_final=''):
    exigir(usuario,'emitir_fiscal')
    if operacao != Operacao.SAIDA:raise ErroFiscal('Use a solicitação de entrada com fornecedor e itens para emitir uma NF-e de entrada.')
    if cfop:validar_cfop(cfop, Operacao.SAIDA)
    if aliquota_icms is not None:
        aliquota_icms=Decimal(str(aliquota_icms))
        if not aliquota_icms.is_finite() or not 0<=aliquota_icms<=100:raise ErroFiscal('Alíquota de ICMS inválida.')
    if natureza_operacao and len(natureza_operacao)>60:raise ErroFiscal('Natureza da operação deve ter até 60 caracteres.')
    if bool(venda_id)==bool(os_id):raise ErroFiscal('Selecione uma venda ou uma OS.')
    config=ConfiguracaoFiscal.objects.select_for_update(of=('self',)).filter(pk=1).first()
    if not config:raise ErroFiscal('Cadastre a configuração fiscal desta instalação.')
    serie=config.serie_padrao if serie is None else serie
    if not isinstance(serie,int) or not 1<=serie<=999:raise ErroFiscal('Série fiscal inválida.')
    habilitado(config)
    from vendas.models import Venda
    from comercial.models import Documento
    ordem=None
    if os_id:
        if not usuario.has_perm('comercial.view_documento'):raise PermissionDenied
        ordem=Documento.objects.select_for_update(of=('self',)).select_related('cliente','venda').get(pk=os_id,tipo='os')
        if ordem.status not in ('finalizada','entregue','convertido'):
            raise ErroFiscal('Solicite o tratamento fiscal de uma OS concluída ou convertida em venda.')
        origem=ordem.venda if ordem.venda_id else ordem
    else:
        if not usuario.has_perm('vendas.view_venda'):raise PermissionDenied
        origem=Venda.objects.select_for_update(of=('self',)).select_related('cliente').get(pk=venda_id)
        if origem.vendedor_id!=usuario.pk and not usuario.has_perm('vendas.ver_todas_vendas'):raise PermissionDenied
    venda=origem if isinstance(origem,Venda) else None
    if venda and venda.status!='concluida':raise ErroFiscal('A venda deve estar concluída e sem cancelamento/devolução.')
    if venda and not ordem:
        ordem=Documento.objects.filter(venda=venda,tipo='os').first()
    modelo=modelo or config.modelo_mercadorias
    if modelo not in Modelo.values:raise ErroFiscal('Modelo fiscal inválido.')
    if modelo in ('55','65'):
        existentes=DocumentoFiscal.objects.filter(configuracao=config,ambiente=config.ambiente,modelo__in=['55','65'])
        existentes=existentes.filter(venda=venda) if venda else existentes.filter(ordem_servico=ordem)
        existente=existentes.first()
        if existente:
            if existente.modelo!=modelo:raise ErroFiscal('Esta operação já possui documento de mercadoria em outro modelo.')
            return existente
    existente=DocumentoFiscal.objects.filter(configuracao=config,ambiente=config.ambiente,modelo=modelo)
    existente=(existente.filter(venda=venda) if venda else existente.filter(ordem_servico=ordem)).first()
    if existente:return existente
    itens=list(origem.itens.select_related('peca','servico').order_by('pk'))
    snapshot,total=_snapshot(config,origem,itens,modelo,destinatario,cfop,natureza_operacao,aliquota_icms,ind_final,valor_frete,difal,transporte,observacao_final)
    if config.ambiente==Ambiente.PRODUCAO:
        from .prontidao import validar_snapshot_producao
        validar_snapshot_producao(snapshot,modelo,Operacao.SAIDA,timezone.localdate().year)
    sequencia,_=SequenciaFiscal.objects.get_or_create(configuracao=config,modelo=modelo,ambiente=config.ambiente,serie=serie)
    sequencia=SequenciaFiscal.objects.select_for_update(of=('self',)).get(pk=sequencia.pk)
    if sequencia.proximo_numero>999999999:raise ErroFiscal('Numeração fiscal esgotada.')
    numero=sequencia.proximo_numero
    if EventoFiscal.objects.filter(configuracao=config,modelo=modelo,ambiente=config.ambiente,serie=serie,
            tipo='inutilizacao',ano=timezone.localdate().year,numero_inicial__lte=numero,numero_final__gte=numero).exists():
        raise ErroFiscal('A próxima numeração pertence a uma faixa de inutilização. Configure a sequência seguinte.')
    doc=DocumentoFiscal.objects.create(configuracao=config,venda=venda,ordem_servico=ordem,solicitado_por=usuario,
        modelo=modelo,ambiente=config.ambiente,serie=serie,numero=numero,total=total,snapshot=snapshot,status=Status.PENDENTE)
    sequencia.proximo_numero+=1;sequencia.save(update_fields=['proximo_numero'])
    if modelo in ('55','65'):
        doc.chave_acesso=chave_nfe(doc);doc.save(update_fields=['chave_acesso'])
    return doc


def _registrar(doc, operacao, resultado=None, erro=False, evento=None):
    return TentativaTransmissao.objects.create(documento=doc,evento=evento,operacao=operacao,
        pedido_sha256=hashlib.sha256((evento.xml if evento else doc.xml_assinado).encode()).hexdigest(),
        resposta=resposta_sanitizada(resultado.resposta) if resultado else '',
        codigo=resultado.codigo[:20] if resultado else '',
        mensagem=resposta_sanitizada(resultado.mensagem)[:500] if resultado else 'Falha técnica fiscal; operação comercial preservada.',erro_tecnico=erro)


def _aplicar(doc, resultado, consulta=False):
    if doc.status==Status.CANCELADA:return
    if resultado.status=='nao_solicitada':
        if doc.status not in (Status.AUTORIZADA,Status.CANCELAMENTO_PENDENTE):
            doc.status=Status.PENDENTE;doc.transmissao_incerta=False
    elif resultado.status in (Status.AUTORIZADA,Status.CANCELADA):
        if not resultado.protocolo and resultado.status==Status.AUTORIZADA:
            raise ErroFiscal('A autoridade fiscal não retornou protocolo de autorização.')
        doc.status=resultado.status;doc.transmissao_incerta=False
        if resultado.protocolo:doc.protocolo=resultado.protocolo
        if resultado.xml and resultado.status==Status.AUTORIZADA:doc.xml_autorizado=resultado.xml
        if resultado.chave:doc.chave_acesso=resultado.chave
        if resultado.status==Status.AUTORIZADA:doc.autorizado_em=doc.autorizado_em or timezone.now()
    elif doc.status not in (Status.AUTORIZADA,Status.CANCELAMENTO_PENDENTE):
        doc.status=resultado.status
        # Rejeições de duplicidade exigem consulta, nunca uma nova emissão/número.
        doc.transmissao_incerta=resultado.status=='pendente' or resultado.codigo in ('204','539')
    doc.recibo=resultado.recibo or doc.recibo
    doc.codigo_resposta=resultado.codigo[:20];doc.mensagem=resposta_sanitizada(resultado.mensagem)[:500]
    doc.processamento_iniciado_em=None;doc.save()


def transmitir(usuario, documento_id):
    exigir(usuario,'emitir_fiscal')
    with transaction.atomic():
        doc=DocumentoFiscal.objects.select_for_update(of=('self',)).select_related('configuracao').get(pk=documento_id)
        habilitado(doc.configuracao,doc.ambiente)
        if doc.status in (Status.AUTORIZADA,Status.CANCELADA,Status.CANCELAMENTO_PENDENTE):return doc
        if doc.transmissao_incerta or doc.status==Status.PROCESSANDO:
            raise ErroFiscal('A transmissão anterior pode ter sido recebida. Consulte a situação antes de reenviar.')
        if not doc.xml_assinado:
            try:
                xml,ident,qr=gerar_documento(doc,doc.configuracao)
                doc.xml_assinado=xml;doc.qr_code=qr
                if doc.modelo=='nfse':doc.identificador_dps=ident
                else:doc.chave_acesso=ident
            except ErroFiscal as erro:
                doc.status=Status.ERRO_TECNICO;doc.mensagem=str(erro);doc.save()
                _registrar(doc,'preparar',erro=True)
                return doc
        doc.status=Status.PROCESSANDO;doc.transmissao_incerta=True
        doc.processamento_iniciado_em=timezone.now();doc.save()
        tentativa=_registrar(doc,'emitir')
    try:
        resultado=provedor(doc).emitir(doc.configuracao,doc)
        with transaction.atomic():
            doc=DocumentoFiscal.objects.select_for_update(of=('self',)).get(pk=doc.pk)
            _aplicar(doc,resultado)
            tentativa.codigo=resultado.codigo[:20];tentativa.mensagem=resposta_sanitizada(resultado.mensagem)[:500]
            tentativa.resposta=resposta_sanitizada(resultado.resposta);tentativa.save()
    except Exception:
        # Não registrar repr/str de exceções de rede ou de bibliotecas com segredos.
        with transaction.atomic():
            doc=DocumentoFiscal.objects.select_for_update(of=('self',)).get(pk=doc.pk)
            if doc.status==Status.PROCESSANDO:
                doc.status=Status.ERRO_TECNICO;doc.mensagem='Resultado da transmissão desconhecido. Consulte antes de retransmitir.';doc.save()
            tentativa.erro_tecnico=True;tentativa.mensagem='Falha técnica; consulte a autoridade fiscal.';tentativa.save()
    return doc


@transaction.atomic
def atualizar_parametros(usuario, documento_id):
    exigir(usuario,'emitir_fiscal')
    doc=DocumentoFiscal.objects.select_for_update(of=('self',)).get(pk=documento_id)
    if doc.transmissao_incerta or doc.status not in (Status.PENDENTE,Status.REJEITADA,Status.ERRO_TECNICO):
        raise ErroFiscal('Só é possível corrigir parâmetros de uma nota sem autorização ou transmissão incerta.')
    origem=doc.venda if doc.venda_id else doc.ordem_servico
    itens={i.pk:i for i in origem.itens.all()} if origem else {}
    from django.forms.models import model_to_dict
    for linha in doc.snapshot['itens']:
        item=itens.get(linha['origem_item'])
        entrada=doc.operacao==Operacao.ENTRADA
        if not item and not entrada:raise ErroFiscal('Item de origem indisponível; valores fiscais não foram alterados.')
        try:
            params=ParametroServico.objects.get(servico_id=item.servico_id) if doc.modelo=='nfse' else parametro_para_nota(doc.configuracao,linha['peca_id'] if entrada else item.peca_id, doc.operacao)
        except (ParametroServico.DoesNotExist,ParametroProduto.DoesNotExist):
            raise ErroFiscal('Cadastre os parâmetros fiscais do item para esta operação.') from None
        fiscal=dados_fiscais(params)
        if doc.modelo!='nfse':
            informado=linha.get('cfop_personalizado') or doc.snapshot.get('cfop_nota')
            fiscal['cfop']=cfop_saida(params,doc.configuracao,doc.snapshot.get('destinatario',{}),informado) if doc.operacao==Operacao.SAIDA else validar_cfop(informado or fiscal['cfop'],doc.operacao)
            destino={'1':'1','2':'2','3':'3','5':'1','6':'2','7':'3'}[fiscal['cfop'][0]]
            if destino!=doc.snapshot.get('id_destino','1'):raise ErroFiscal('O CFOP atualizado altera o destino da nota. Revise a operação.')
        if doc.modelo!='nfse' and doc.snapshot.get('aliquota_icms_nota') is not None:
            fiscal['aliquota_icms']=doc.snapshot['aliquota_icms_nota']
        linha['fiscal']=fiscal
    doc.xml_assinado='';doc.status=Status.PENDENTE;doc.mensagem='Parâmetros fiscais atualizados; valores e numeração preservados.'
    doc.save(update_fields=['snapshot','xml_assinado','status','mensagem','atualizado_em'])
    return doc


@transaction.atomic
def ativar_contingencia(usuario, documento_id, justificativa):
    exigir(usuario,'emitir_fiscal')
    doc=DocumentoFiscal.objects.select_for_update(of=('self',)).select_related('configuracao').get(pk=documento_id)
    habilitado(doc.configuracao,doc.ambiente)
    if doc.modelo!='65' or doc.configuracao.qr_code_versao!='3':
        raise ErroFiscal('Contingência offline disponível para NFC-e com QR Code 3.00.')
    if doc.transmissao_incerta or doc.xml_assinado or doc.status not in (Status.PENDENTE,Status.ERRO_TECNICO):
        raise ErroFiscal('Não altere o tipo de emissão de uma nota já assinada ou transmitida.')
    if not 15<=len(justificativa.strip())<=255:raise ErroFiscal('Justificativa de 15 a 255 caracteres necessária.')
    doc.tipo_emissao='9';doc.status=Status.CONTINGENCIA
    doc.snapshot['contingencia_justificativa']=justificativa.strip()
    doc.chave_acesso=chave_nfe(doc)
    doc.xml_assinado,doc.chave_acesso,doc.qr_code=gerar_documento(doc,doc.configuracao)
    doc.save()
    EventoFiscal.objects.create(documento=doc,configuracao=doc.configuracao,operador=usuario,tipo='contingencia',
        modelo=doc.modelo,ambiente=doc.ambiente,serie=doc.serie,status=Status.CONTINGENCIA,justificativa=justificativa.strip())
    return doc


def consultar(usuario, documento_id):
    exigir(usuario,'consultar_fiscal')
    doc=DocumentoFiscal.objects.select_related('configuracao').get(pk=documento_id)
    habilitado(doc.configuracao,doc.ambiente)
    if not (doc.chave_acesso or doc.identificador_dps):raise ErroFiscal('Documento ainda sem identificador fiscal para consulta.')
    if doc.status==Status.PROCESSANDO and doc.processamento_iniciado_em and (timezone.now()-doc.processamento_iniciado_em).total_seconds()<90:
        raise ErroFiscal('Transmissão em andamento. Aguarde a conclusão antes de consultar.')
    try:
        resultado=provedor(doc).consultar(doc.configuracao,doc)
        with transaction.atomic():
            doc=DocumentoFiscal.objects.select_for_update(of=('self',)).get(pk=doc.pk)
            _registrar(doc,'consultar',resultado);_aplicar(doc,resultado,consulta=True)
            if doc.status==Status.CANCELADA:
                doc.eventos.filter(tipo='cancelamento').update(status=Status.CANCELADA)
    except ErroFiscal:
        _registrar(doc,'consultar',erro=True)
        raise
    return doc


@transaction.atomic
def solicitar_cancelamento(usuario, documento_id, justificativa):
    exigir(usuario,'cancelar_fiscal')
    if not 15<=len(justificativa.strip())<=255:raise ErroFiscal('A justificativa deve ter de 15 a 255 caracteres.')
    doc=DocumentoFiscal.objects.select_for_update(of=('self',)).select_related('configuracao').get(pk=documento_id)
    habilitado(doc.configuracao,doc.ambiente)
    existente=doc.eventos.filter(tipo='cancelamento').first()
    if existente:return existente
    if doc.status!=Status.AUTORIZADA or not doc.protocolo:raise ErroFiscal('Somente um documento autorizado pode ser cancelado.')
    evento=EventoFiscal.objects.create(documento=doc,configuracao=doc.configuracao,operador=usuario,tipo='cancelamento',
        ambiente=doc.ambiente,modelo=doc.modelo,serie=doc.serie,justificativa=justificativa.strip(),status=Status.PENDENTE)
    doc.status=Status.CANCELAMENTO_PENDENTE;doc.save(update_fields=['status'])
    return evento


@transaction.atomic
def solicitar_correcao(usuario,documento_id,texto,chave):
    exigir(usuario,'emitir_fiscal')
    texto=' '.join(texto.split())
    if not 15<=len(texto)<=1000:raise ErroFiscal('A correção deve ter de 15 a 1000 caracteres.')
    doc=DocumentoFiscal.objects.select_for_update(of=('self',)).select_related('configuracao').get(pk=documento_id)
    habilitado(doc.configuracao,doc.ambiente)
    if doc.modelo!='55' or doc.status!=Status.AUTORIZADA or not doc.protocolo:raise ErroFiscal('CC-e disponível somente para NF-e autorizada e não cancelada.')
    existente=doc.eventos.filter(tipo='correcao',idempotencia=chave).first()
    if existente:return existente
    if doc.eventos.filter(tipo='correcao',status__in=[Status.PENDENTE,Status.PROCESSANDO,Status.ERRO_TECNICO]).exists():
        raise ErroFiscal('Conclua ou consulte a CC-e anterior antes de criar outra.')
    from django.db.models import Max
    sequencia=(doc.eventos.filter(tipo='correcao').aggregate(valor=Max('sequencia'))['valor'] or 0)+1
    if sequencia>20:raise ErroFiscal('Limite de 20 sequências de CC-e atingido para esta nota.')
    return EventoFiscal.objects.create(documento=doc,configuracao=doc.configuracao,operador=usuario,tipo='correcao',
        idempotencia=chave,ambiente=doc.ambiente,modelo=doc.modelo,serie=doc.serie,sequencia=sequencia,texto_correcao=texto,status=Status.PENDENTE)


@transaction.atomic
def solicitar_inutilizacao(usuario, modelo, serie, inicio, fim, ano, justificativa):
    exigir(usuario,'inutilizar_fiscal')
    if modelo not in ('55','65') or not (1<=inicio<=fim<=999999999 and 1<=serie<=999) or not 15<=len(justificativa.strip())<=255:
        raise ErroFiscal('Informe uma faixa válida de NF-e/NFC-e e justificativa de 15 a 255 caracteres.')
    if ano not in (timezone.localdate().year,timezone.localdate().year-1):raise ErroFiscal('Ano de inutilização inválido.')
    config=ConfiguracaoFiscal.objects.select_for_update(of=('self',)).get(pk=1);habilitado(config)
    if DocumentoFiscal.objects.filter(configuracao=config,modelo=modelo,ambiente=config.ambiente,serie=serie,
        emitido_em__year=ano,numero__range=(inicio,fim)).exists():raise ErroFiscal('A faixa contém documentos fiscais já reservados.')
    existente=EventoFiscal.objects.filter(configuracao=config,modelo=modelo,ambiente=config.ambiente,serie=serie,
        tipo='inutilizacao',ano=ano,numero_inicial__lte=fim,numero_final__gte=inicio).first()
    if existente:
        if existente.numero_inicial==inicio and existente.numero_final==fim:return existente
        raise ErroFiscal('A faixa sobrepõe outra solicitação de inutilização.')
    return EventoFiscal.objects.create(configuracao=config,operador=usuario,tipo='inutilizacao',modelo=modelo,
        ambiente=config.ambiente,serie=serie,numero_inicial=inicio,numero_final=fim,ano=ano,justificativa=justificativa.strip())


def transmitir_evento(usuario, evento_id):
    with transaction.atomic():
        ev=EventoFiscal.objects.select_for_update(of=('self',)).select_related('configuracao','documento').get(pk=evento_id)
        if ev.tipo not in ('cancelamento','inutilizacao','correcao'):
            raise ErroFiscal('Este evento é apenas um registro local, sem transmissão própria.')
        exigir(usuario,{'cancelamento':'cancelar_fiscal','correcao':'emitir_fiscal','inutilizacao':'inutilizar_fiscal'}[ev.tipo])
        habilitado(ev.configuracao,ev.ambiente)
        if ev.status in (Status.CANCELADA,Status.AUTORIZADA):return ev
        if ev.status in (Status.PROCESSANDO,Status.ERRO_TECNICO):raise ErroFiscal('Resultado do evento incerto. Consulte antes de repetir.')
        if ev.tipo=='correcao':
            if ev.documento.status!=Status.AUTORIZADA:raise ErroFiscal('CC-e exige NF-e ainda autorizada e não cancelada.')
            if ev.codigo_resposta in ('136','573'):raise ErroFiscal('Consulte o registro da CC-e anterior antes de repetir o envio.')
        if ev.tipo=='correcao' and not ev.xml:
            from .cartas import gerar_xml
            ev.xml=gerar_xml(ev.configuracao,ev.documento,ev);ev.save(update_fields=['xml'])
        ev.status=Status.PROCESSANDO;ev.save(update_fields=['status'])
        tentativa=TentativaTransmissao.objects.create(evento=ev,documento=ev.documento,operacao=ev.tipo)
    try:
        adaptador=provedor(ev)
        if ev.tipo=='correcao':r=adaptador.corrigir(ev.configuracao,ev.documento,ev)
        elif ev.tipo=='cancelamento':r=adaptador.cancelar(ev.configuracao,ev.documento,ev)
        else:r=adaptador.inutilizar(ev.configuracao,ev)
        with transaction.atomic():
            ev=EventoFiscal.objects.select_for_update(of=('self',)).get(pk=ev.pk)
            ev.status=r.status;ev.xml_autorizado=r.xml or ev.xml_autorizado;ev.protocolo=r.protocolo;ev.codigo_resposta=r.codigo[:20];ev.mensagem=resposta_sanitizada(r.mensagem)[:500];ev.save()
            tentativa.codigo=r.codigo[:20];tentativa.resposta=resposta_sanitizada(r.resposta);tentativa.pedido_sha256=hashlib.sha256(ev.xml.encode()).hexdigest();tentativa.save()
            if ev.documento_id and r.status==Status.CANCELADA:
                doc=DocumentoFiscal.objects.select_for_update(of=('self',)).get(pk=ev.documento_id);doc.status=Status.CANCELADA;doc.save(update_fields=['status'])
    except Exception:
        ev.status=Status.ERRO_TECNICO;ev.mensagem='Evento sem confirmação. Consulte a autoridade fiscal antes de repetir.';ev.save(update_fields=['status','mensagem'])
        tentativa.erro_tecnico=True;tentativa.mensagem='Falha técnica no evento fiscal.';tentativa.save()
    return ev


def consultar_evento(usuario, evento_id):
    exigir(usuario,'consultar_fiscal')
    ev=EventoFiscal.objects.select_related('documento','configuracao').get(pk=evento_id)
    if ev.tipo=='correcao':
        if ev.status==Status.AUTORIZADA:return ev
        habilitado(ev.configuracao,ev.ambiente)
        ultima=ev.tentativas.order_by('-criado_em').first()
        if ultima and (timezone.now()-ultima.criado_em).total_seconds()<90:raise ErroFiscal('Aguarde a conclusão do envio antes de consultar a CC-e.')
        r=provedor(ev).consultar_correcao(ev.configuracao,ev.documento,ev)
        with transaction.atomic():
            ev=EventoFiscal.objects.select_for_update(of=('self',)).get(pk=ev.pk)
            ev.status=r.status;ev.protocolo=r.protocolo;ev.codigo_resposta=r.codigo[:20];ev.mensagem=resposta_sanitizada(r.mensagem)[:500];ev.xml_autorizado=r.xml or ev.xml_autorizado;ev.save()
            TentativaTransmissao.objects.create(evento=ev,documento=ev.documento,operacao='consultar_correcao',codigo=r.codigo[:20],mensagem=ev.mensagem,resposta=resposta_sanitizada(r.resposta))
        return ev
    if ev.tipo!='cancelamento':
        raise ErroFiscal('Consulte a inutilização no portal oficial da SEFAZ; o serviço não oferece consulta por faixa.')
    if ev.status in (Status.CANCELADA,Status.AUTORIZADA):return ev
    ultima=ev.tentativas.order_by('-criado_em').first()
    if ultima and (timezone.now()-ultima.criado_em).total_seconds()<90:
        raise ErroFiscal('Aguarde a conclusão do envio antes de consultar o evento.')
    doc=consultar(usuario,ev.documento_id)
    with transaction.atomic():
        ev=EventoFiscal.objects.select_for_update(of=('self',)).get(pk=ev.pk)
        if doc.status==Status.CANCELADA:
            ev.status=Status.CANCELADA
        elif doc.status==Status.AUTORIZADA and doc.codigo_resposta in ('100','150'):
            ev.status=Status.PENDENTE
            ev.mensagem='Nota permanece autorizada. O mesmo evento pode ser reenviado.'
        ev.save(update_fields=['status','mensagem'])
    return ev
