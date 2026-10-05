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
                     EventoFiscal, ParametroProduto, ParametroServico, SequenciaFiscal, TentativaTransmissao)
from .provedores import provedor
from .seguranca import ErroFiscal, resposta_sanitizada
from .xml import gerar_documento, chave_nfe, valor


def exigir(usuario, permissao):
    if not usuario.is_authenticated or not usuario.has_perm('fiscal.'+permissao):
        raise PermissionDenied


def habilitado(config, ambiente=None):
    if not settings.FISCAL_ENABLED or not config.ativa:
        raise ErroFiscal('O módulo fiscal está desativado nesta instalação.')
    ambiente = ambiente or config.ambiente
    if ambiente == Ambiente.PRODUCAO and not (settings.FISCAL_ALLOW_PRODUCTION and config.homologacao_validada and config.producao_validada):
        raise ErroFiscal('Emissão em produção bloqueada. Valide a homologação e libere explicitamente esta instalação.')


def _snapshot(config, origem, itens, modelo, destinatario):
    from django.forms.models import model_to_dict
    empresa = {k: getattr(config,k) for k in ('cnpj','razao_social','nome_fantasia','ie','im','crt','uf',
        'municipio_ibge','municipio','logradouro','numero','bairro','cep','natureza_operacao')}
    cliente = origem.cliente
    dados_dest = {'nome':cliente.nome if cliente else getattr(origem,'cliente_nome',''),
                  'documento':re.sub(r'\D','',cliente.documento) if cliente else ''}
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
    linhas=[]
    for i in selecionados:
        try:
            params = (ParametroServico.objects.get(servico_id=i.servico_id) if modelo==Modelo.NFSE
                      else ParametroProduto.objects.get(peca_id=i.peca_id))
        except (ParametroProduto.DoesNotExist,ParametroServico.DoesNotExist):
            raise ErroFiscal('Cadastre os parâmetros fiscais de todos os itens selecionados.') from None
        fiscal=model_to_dict(params,exclude=['id','peca','servico','criado_em','atualizado_em'])
        fiscal={k:str(v) if isinstance(v,Decimal) else v for k,v in fiscal.items()}
        preco=Decimal(getattr(i,'preco_unitario',getattr(i,'preco',0)))
        bruto=preco*i.quantidade
        desconto=Decimal(i.desconto) if rateios is None else rateios[itens.index(i)]
        total=bruto-desconto
        linhas.append({'origem_item':i.pk,'codigo':str(i.servico.codigo if i.servico_id else i.peca.codigo),
            'descricao':i.descricao,'quantidade':i.quantidade,'preco_unitario':str(preco),
            'bruto':valor(bruto),'desconto':valor(desconto),'total':valor(total),'fiscal':fiscal})
    return {'empresa':empresa,'destinatario':dados_dest,'itens':linhas,'origem_codigo':origem.codigo}, sum((Decimal(i['total']) for i in linhas),Decimal('0'))


@transaction.atomic
def solicitar(usuario, *, venda_id=None, os_id=None, modelo=None, serie=1, destinatario=None):
    exigir(usuario,'emitir_fiscal')
    if not isinstance(serie,int) or not 1<=serie<=999:raise ErroFiscal('Série fiscal inválida.')
    if bool(venda_id)==bool(os_id):raise ErroFiscal('Selecione uma venda ou uma OS.')
    config=ConfiguracaoFiscal.objects.select_for_update(of=('self',)).filter(pk=1).first()
    if not config:raise ErroFiscal('Cadastre a configuração fiscal desta instalação.')
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
    snapshot,total=_snapshot(config,origem,itens,modelo,destinatario)
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
    itens={i.pk:i for i in origem.itens.all()}
    from django.forms.models import model_to_dict
    for linha in doc.snapshot['itens']:
        item=itens.get(linha['origem_item'])
        if not item:raise ErroFiscal('Item de origem indisponível; valores fiscais não foram alterados.')
        try:
            params=ParametroServico.objects.get(servico_id=item.servico_id) if doc.modelo=='nfse' else ParametroProduto.objects.get(peca_id=item.peca_id)
        except (ParametroServico.DoesNotExist,ParametroProduto.DoesNotExist):
            raise ErroFiscal('Cadastre os parâmetros fiscais do item.') from None
        fiscal=model_to_dict(params,exclude=['id','peca','servico','criado_em','atualizado_em'])
        linha['fiscal']={k:str(v) if isinstance(v,Decimal) else v for k,v in fiscal.items()}
    doc.xml_assinado='';doc.status=Status.PENDENTE;doc.mensagem='Parâmetros fiscais atualizados; valores e numeração preservados.'
    doc.save(update_fields=['snapshot','xml_assinado','status','mensagem'])
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
        if ev.tipo not in ('cancelamento','inutilizacao'):
            raise ErroFiscal('Este evento é apenas um registro local, sem transmissão própria.')
        exigir(usuario,'cancelar_fiscal' if ev.tipo=='cancelamento' else 'inutilizar_fiscal')
        habilitado(ev.configuracao,ev.ambiente)
        if ev.status in (Status.CANCELADA,Status.AUTORIZADA):return ev
        if ev.status in (Status.PROCESSANDO,Status.ERRO_TECNICO):raise ErroFiscal('Resultado do evento incerto. Consulte antes de repetir.')
        ev.status=Status.PROCESSANDO;ev.save(update_fields=['status'])
        tentativa=TentativaTransmissao.objects.create(evento=ev,documento=ev.documento,operacao=ev.tipo)
    try:
        adaptador=provedor(ev)
        r=adaptador.cancelar(ev.configuracao,ev.documento,ev) if ev.tipo=='cancelamento' else adaptador.inutilizar(ev.configuracao,ev)
        with transaction.atomic():
            ev=EventoFiscal.objects.select_for_update(of=('self',)).get(pk=ev.pk)
            ev.status=r.status;ev.protocolo=r.protocolo;ev.codigo_resposta=r.codigo[:20];ev.mensagem=resposta_sanitizada(r.mensagem)[:500];ev.save()
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
