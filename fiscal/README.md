# Fiscal REGISTER

NF-e (55) suporta os endpoints oficiais da SEFAZ-SP em homologação e produção. Produção exige flags e validações explícitas da instalação; NFC-e continua restrita a homologação. Uma prévia é salva como rascunho por usuário, sem numeração; a reserva e a transmissão são ações separadas.

Em **Configurações fiscais / Testar conexão SEFAZ**, selecione NF-e ou NFC-e após salvar UF SP, ambiente homologação e A1. A ação exige permissão de configuração e POST com CSRF. Pode ser usada com a emissão desativada: envia apenas `consStatServ` 4.00 (`tpAmb=2`, `cUF=35`, `xServ=STATUS`) por SOAP 1.2 e autenticação mTLS, conforme MOC 7.0 §5.5. Não assina o XML de status, não emite notas, não reserva série/número e não grava documentos/eventos. O resultado conectado exige `cStat=107`, ambiente/UF/versão e campos obrigatórios compatíveis. Os endereços são fixados no código a partir dos portais oficiais citados ao final; overrides diferentes são recusados. Não foram criados esquemas XML próprios.

Módulo aditivo: mantém seus próprios modelos, migrations, permissões, configurações, sequências e auditoria. Não há sinais de emissão automática nem alterações nos serviços comerciais. Venda/OS finalizada pode originar documentos separados de mercadorias e serviços. Venda convertida de OS compartilha a mesma solicitação. Rejeição, cancelamento fiscal e falha de comunicação não modificam venda, estoque, caixa ou financeiro.

## Instalação e homologação

1. Instalar `requirements.lock` e executar `python manage.py migrate fiscal` em **cada instalação**, após conferir o plano de migrations e realizar backup.
2. Criar uma chave Fernet dedicada com `cryptography.fernet.Fernet.generate_key()` e armazenar em `FISCAL_SECRET_KEY` no gerenciador de segredos da instalação. Não usar a chave Django, não incluir a chave no Git e preservar uma cópia protegida para recuperação do banco. Certificado A1, senha e CSC são criptografados no banco. Loja 1 e Loja 2 devem ter configurações e chaves próprias; bancos compartilhados não constituem instalações fiscais independentes.
3. Conceder individualmente `fiscal.configurar_fiscal`, `fiscal.emitir_fiscal`, `fiscal.cancelar_fiscal`, `fiscal.consultar_fiscal` e, quando necessário, `fiscal.inutilizar_fiscal`. Nenhum grupo operacional recebe automaticamente autorização fiscal.
4. Em **Fiscal / Configurações fiscais**, preencher empresa, regime, endereço, A1, série, endpoints e parâmetros de produtos/serviços. Configurar `FISCAL_ENABLED=True` somente para a instalação em validação e marcar a configuração ativa, mantendo o ambiente **homologação**. Os padrões permanecem desativados e `FISCAL_ALLOW_PRODUCTION=False`.
5. Validar com certificado e cadastro reais no autorizador competente: emissão, consulta, rejeição, retransmissão, cancelamento, inutilização, QR Code, contingência e documento auxiliar. Testes locais usam certificados sintéticos e serviços simulados; **não são homologação real**.

Produção exige liberação explícita de `FISCAL_ALLOW_PRODUCTION`, homologação validada, produção validada e escolha do ambiente na configuração. O sistema não libera nem realiza emissão real automaticamente. Uma mudança de ambiente não altera o ambiente de documentos já reservados.

## Operação

O menu Fiscal segue os componentes e estilos existentes. Os links acrescentados às vendas/OS apenas abrem a solicitação fiscal. Informe o modelo, série e, para NF-e/NFS-e, os dados fiscais/endereço do destinatário. Esses dados ficam no documento e não alteram o cadastro comercial do cliente.

Uma solicitação reserva uma numeração em transação e congela os valores, empresa e itens de origem. Repetir a solicitação retorna o documento existente. Transmissão utiliza sua mesma chave/numeração; autorização nunca é retransmitida. Após resultado desconhecido, a emissão fica bloqueada até consulta que confirme a situação. Não criar outra nota para contornar esse bloqueio.

Correções de parâmetros tributários são permitidas somente antes de autorização e sem transmissão incerta, preservando valores e número. Cancelar fiscalmente não cancela a venda. NFC-e permite contingência offline explicitamente solicitada, com QR Code 3.00, antes da primeira assinatura/transmissão; continua exigindo autorização posterior e regras/prazos da UF.

Cancelamento com resposta desconhecida deve ser consultado antes de repetir o mesmo evento. Inutilização sem confirmação permanece bloqueada; verificar no portal oficial da SEFAZ, pois o webservice de inutilização não oferece consulta por faixa. Não registrar autorização sem comprovante oficial.

Processamento também pode ser solicitado explicitamente por operador autorizado:

```text
python manage.py fiscal_processar --usuario OPERADOR --documento ID
python manage.py fiscal_processar --usuario OPERADOR --documento ID --consultar
python manage.py fiscal_processar --usuario OPERADOR --evento ID
python manage.py fiscal_processar --usuario OPERADOR --evento ID --consultar
```

## Comunicação oficial e limites de homologação

NF-e/NFC-e usam SOAP 1.2 e mTLS diretamente na SEFAZ. Os endpoints padrão são de SP; outras UFs/autorizadores exigem configuração dos serviços oficiais. `endpoints` usa a estrutura `{ambiente: {modelo: {operacao: URL}}}`, com ambientes `homologacao`/`producao`, modelos `55`/`65`/`nfse` e operações `emitir`, `consultar`, `recibo`, `cancelar`, `inutilizar`; NFC-e também `qr_code` e `consulta_publica`. URLs devem ser HTTPS oficiais; exceções explícitas de hosts usam `FISCAL_ENDPOINT_HOSTS`. Homologação requer host identificado como homologação/teste/produção restrita, prevenindo envio acidental à produção.

NFC-e suporta QR Code 3.00 (online sem CSC; offline assinado) e 2.00 com CSC criptografado, vinculado ao ambiente. O endereço de consulta/QR depende da UF.

NFS-e usa diretamente a API SEFIN Nacional com DPS 1.01 e certificado A1, para municípios aderentes. `parametros_nfse` deve conter `municipio_conveniado: true`; demais parâmetros seguem o gerador DPS. Municípios que exigem serviços próprios precisam de adaptador direto específico, configurado em `FISCAL_NFSE_ADAPTER`, com métodos `emitir(config, documento)`, `consultar(config, documento)` e `cancelar(config, documento, evento)`, retornando `fiscal.provedores.Resultado`. Não existe API paga obrigatória. Serviços com parâmetros incompatíveis na mesma operação são bloqueados em vez de produzir DPS incorreta.

O gerador inicial contempla operações comuns com CSOSN 102/103/300/400 ou CST ICMS 00, PIS/COFINS 01/02 e situações não tributadas previstas no código. ST, benefícios, importação, desoneração, partilhas e demais cenários precisam de implementação/validação tributária específica antes de uso; não são deduzidos do cadastro comercial. Grupos adicionais não substituem essa validação, inclusive IBS/CBS e totais exigidos pela legislação aplicável.

O documento auxiliar local oferece identificação, itens, valores, chave e QR Code. Seu leiaute precisa de conferência fiscal e visual em homologação antes de uso em produção. Para NFS-e autorizada, um endpoint oficial `danfse` configurado permite obter o PDF oficial. Documentos de teste/não autorizados são identificados como sem valor fiscal. A impressão comercial de etiquetas não foi modificada.

## Esquemas e segurança

XMLs de documentos e eventos são assinados e validados contra XSD antes de transmissão. `fiscal/schemas/fontes.json` registra URLs e SHA-256 dos arquivos: pacote oficial NF-e 010e e NFS-e 1.01, com esquemas de envelope/eventos complementados pelo repositório público NFePHP. Não é permitido DTD, entidade externa, redirecionamento HTTP ou TLS sem verificação. O comando `fiscal_importar_schemas` importa somente XSD de ZIP verificado, sem caminhos externos.

O pacote NFS-e 1.01 publica a expressão de série `^0{0,4}\d{1,5}$`, incompatível com a semântica de regex XML Schema usada por libxml2. O carregador adapta **somente essa expressão em memória** para `0{0,4}\d{1,5}`, preservando o arquivo oficial e seus limites numéricos.

Certificados privados/segredos não são gravados em logs nem servidos por download. Chaves temporárias de mTLS permanecem criptografadas e são removidas ao concluir a conexão. XML e documentos ficam restritos à permissão de consulta. Respostas de auditoria são sanitizadas; certificados/senhas/CSC/tokens são removidos. Alterar a chave Fernet sem processo de migração torna os segredos existentes inacessíveis.

Referências: [SEFAZ-SP NF-e](https://portal.fazenda.sp.gov.br/servicos/nfe/Paginas/URL-WEBSERVICES.aspx), [SEFAZ-SP NFC-e](https://portal.fazenda.sp.gov.br/servicos/nfce/Paginas/WebServices.aspx), [APIs NFS-e](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/apis-prod-restrita-e-producao), [documentação e esquemas NFS-e](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual).


## Status, CC-e e CEP
A página de status apresenta o retorno, chave, protocolo e tentativas. CC-e usa evento 110110, sequências 1–20, assinatura A1 e validação dos XSD; só cStat 135 com chave, ambiente, sequência e protocolo correspondentes confirma registro. A CC-e não cancela a NF-e. Respostas incertas exigem consulta e não permitem novo número/evento para contornar a pendência. Cancelamento e inutilização continuam como eventos distintos.

IBS/CBS normal CST 000/cClassTrib 000001 usa campos próprios e totalização do XML; o cálculo de 2026 considera IBS UF 0,1%, municipal 0% e CBS 0,9%. Outras situações não são aproximadas. A base PIS/COFINS é selecionável; a base IBS/CBS desconta os tributos da regra UB16-10. DIFAL de saída para consumidor final não contribuinte em outra UF suporta CRT 3/CST 00, base integral no preço final, alíquota interna e FCP explícitos por nota. FCP vazio não equivale a zero. Reduções e isenções não são presumidas. O grupo ICMSUFDest e os totais entram no XML; DIFAL e FCP do destino são deduzidos da base IBS/CBS (UB16-10). O imposto já está incluído no preço final e não é somado novamente ao total. A conferência permanece sem numeração e sem transmissão.

O CEP é consultado no ViaCEP por um endpoint autenticado, em URL fixa com 8 dígitos; somente o CEP é enviado. Os dados ficam editáveis. Falha de consulta não impede o preenchimento manual.


## Central fiscal e transporte
A Central reúne rascunhos e notas numeradas com busca comum, filtros de modelo/operação/ambiente e abas por etapa. As rotas antigas continuam disponíveis. Rascunhos de saída e entrada ficam restritos ao usuário, inclusive no salvamento incompleto e na paginação. A tela de preparação salva/confronta a prévia; numeração e transmissão são etapas seguintes.

Transporte da NF-e usa os mesmos campos na saída e na entrada: modalidade (0/1/2/3/4/9), transportador, CPF/CNPJ/IE, endereço, veículo/UF/RNTRC, volumes e pesos em kg com três casas decimais. O XML serializa transportador e volumes conforme o XSD instalado, e a DANFE lê esse XML. Conforme MOC 7.0 X02-20, veicTransp não é enviado nas operações interestaduais: placa e RNTRC permanecem no controle interno do envio, com indicação na conferência. Nas demais operações suportadas, o veículo compõe o grupo correspondente do XML. Dados e frete contraditórios, placa incompleta e peso bruto menor que o líquido são recusados. Registros anteriores sem transporte estruturado mantêm a modalidade já usada pelo emissor (0 quando há frete, 9 nos demais casos).

Notas numeradas podem complementar transporte apenas antes da primeira transmissão e sem XML assinado/autorizado. Essa edição preserva número, total e tributos. Notas transmitidas, com situação incerta ou autorizadas não são reescritas por essa ação. A atualização da interface não emite notas nem cria transportadores fictícios.
