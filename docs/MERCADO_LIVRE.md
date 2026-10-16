# Mercado Livre — etapa 1: conexão e importação somente leitura

Implementação local; não executar deploy/push para a branch de produção sem autorização.

## Escopo entregue

- Aplicação Django `mercadolivre`, banco PostgreSQL e processo web existentes. Sem workers, cron, webhooks ou serviços adicionais.
- OAuth Authorization Code com PKCE S256, state aleatório vinculado à sessão e ao usuário, validade de dez minutos e consumo único no banco. Verificação do vendedor tanto no token quanto em `/users/me`.
- Solicitação de `read offline_access`. Por padrão, tokens com `write` são recusados. Quando a configuração funcional obrigatória do provedor retorna esse escopo global, a loja pode aceitar o formato somente com autorização explícita e `MERCADOLIVRE_PROVIDER_SCOPE_COMPAT=True`. A flag não habilita chamadas de alteração: o transporte continua bloqueando métodos de escrita em todos os recursos de negócio. Os escopos recebidos são registrados no banco, na auditoria de conexão e informados no painel. Leitura, acesso offline e identidade correta continuam obrigatórios. A compatibilidade reconhece os identificadores funcionais nos namespaces `urn:ml:` e `urn:global:`, além dos escopos básicos. Namespace `urn:mp:`, outros produtos, identificadores inválidos e respostas excessivas são recusados. A presença de uma permissão no token não adiciona endpoints ao cliente da API. Desativar a flag bloqueia o uso dos tokens amplos existentes. Configure as permissões funcionais de anúncios no Developers como Leitura.
- Access/refresh tokens cifrados com Fernet (criptografia autenticada); chave independente do SECRET_KEY do Django. Segredo da aplicação somente em variável de ambiente. Tokens não aparecem em formulário, admin, mensagens ou auditoria. O log Gunicorn omite query strings, incluindo o código temporário do callback. Se houver logs de proxy externos, configure-os também para não armazenar query strings do callback.
- Renovação por demanda, com bloqueio de linha PostgreSQL para evitar duas renovações simultâneas. O novo refresh token é salvo antes das consultas de importação, pois o anterior é de uso único. Não há retry automático de troca/renovação; em falha ambígua, reconecte.
- Importação manual em lotes de até 20, usando scan e o novo `/items/bulk` (não utiliza o multiget antigo em descontinuação). Lista anúncios da conta autenticada, inclusive os que ainda não têm vínculo. Salva apenas os campos exibidos e IDs/quantidades das variações; não importa compradores, pedidos ou dados pessoais.
- Reimportação atualiza a fotografia local sem duplicar anúncios ou apagar vínculos. Falha parcial não grava o lote. Se um item não puder ser consultado ou o cursor expirar, reinicie a busca. O cursor tem prazo conservador de quatro minutos desde o início da busca, sem extensão a cada clique. Anúncios ausentes de uma nova busca não são apagados: a data da última consulta fica visível em cada registro.
- Vínculo e remoção manual por código exato da peça na mesma instalação. É possível referenciar vários anúncios na mesma peça; isso não habilita sincronização. Anúncios com variações recebem aviso: vínculo de referência no anúncio completo, sem mapeamento de variação para estoque nesta etapa.
- Opção “Anunciar no Mercado Livre” na tabela e detalhe de cada peça. Abre uma tela que permite apenas selecionar/remover uma intenção local individual. Não existe seleção em massa, endpoint de publicação ou autorização implícita para escrita futura.
- Interface `/mercado-livre/`: conexão, desconexão local, importação, busca paginada, vínculos e até 50 seleções recentes. As demais seleções podem ser consultadas no detalhe de cada peça.
- Permissão `mercadolivre.gerenciar_integracao`; a seleção/vinculação também exige permissões de consulta/alteração da peça. O comando existente `configurar_operacao` concede o acesso apenas ao grupo Administrador. Superusuários já têm acesso. Nenhuma permissão nova é dada automaticamente a Gerente, Caixa ou Vendedor.
- Auditoria sem credenciais para conexão, desconexão, importação, vínculos e seleções. Formulários protegidos por CSRF e ações por POST. Páginas da integração sem cache. Formulários usam `same-origin` para preservar a verificação CSRF em HTTPS; os redirects OAuth usam `no-referrer` para não encaminhar códigos de autorização.

## O que fica para a próxima etapa

Publicação, sincronização de estoque/vendas, atualização de preços/anúncios e pausa não foram ativadas nem implementadas como chamadas de escrita nesta etapa. O transporte bloqueia POST/PUT/PATCH/DELETE em recursos de negócio e não consulta pedidos. Só permite POST para troca/renovação de tokens e GET dos recursos necessários à importação.

As tabelas `Anuncio` e `Selecao` e os vínculos locais preparam a base da próxima etapa, mas não são autorização para alterar anúncios. Uma futura entrega deve exigir nova autorização explícita, mapear variações, separar consentimento para estoque/vendas/preços, validar dados obrigatórios por categoria e assegurar idempotência e concorrência das vendas. Não adicionar sinais automáticos de `Peca.save()` ou `Venda` para publicar/sincronizar todas as peças.

## Variáveis Railway por instalação

| Variável | Valor |
| --- | --- |
| `MERCADOLIVRE_PROVIDER_SCOPE_COMPAT` | `False` por padrão. `True` somente após autorização específica para aceitar o escopo global retornado pelo provedor, com todas as chamadas de alteração bloqueadas. |
| `MERCADOLIVRE_ENABLED` | `True` somente na loja que vai conectar. Padrão `False`. |
| `MERCADOLIVRE_CLIENT_ID` | App ID da aplicação Mercado Livre Developers. |
| `MERCADOLIVRE_CLIENT_SECRET` | Secret Key da aplicação; variável secreta no Railway. |
| `MERCADOLIVRE_SELLER_ID` | ID numérico do titular vendedor esperado. O login de operador/colaborador não substitui a autorização do titular. |
| `MERCADOLIVRE_INSTALLATION_ID` | Identificador exclusivo e estável, por exemplo `pontocar-principal`. |
| `MERCADOLIVRE_REDIRECT_URI` | `https://register-production-351c.up.railway.app/mercado-livre/oauth/callback/` na PontoCar principal. Deve corresponder exatamente à URL registrada no Developers e pertencer a `ALLOWED_HOSTS`. |
| `MERCADOLIVRE_TOKEN_KEY` | Chave Fernet aleatória exclusiva desta loja, guardada como segredo e em backup seguro. |

Para gerar a chave na sua máquina, sem gravá-la no repositório:

```powershell
.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Não colar credenciais reais em arquivos versionados ou no chat. Não configurar access/refresh tokens manualmente no Railway: eles são obtidos no OAuth e armazenados cifrados no PostgreSQL da loja. Preserve a chave ao recriar o serviço/restaurar backups; trocar a chave sem recifrar exige reconectar.

No Developers, habilite Authorization Code, PKCE S256 e os acessos de leitura necessários para consultar conta/anúncios, incluindo acesso offline. Mantenha os recursos configuráveis em Leitura nesta etapa. O Developers pode manter Usuários em Leitura e escrita por padrão; não confundir o escopo global devolvido pelo provedor com permissão para o REGISTER alterar dados. Não há URL de notificações implementada; não enviar webhooks a este callback OAuth. Cadastre a redirect URI exata, com a barra final.

## Independência das lojas

Os bancos, sessões, tokens e vínculos permanecem nas instalações independentes existentes. Não há acesso ao banco, domínio ou bucket de outra loja. Na Loja 2 mantenha `MERCADOLIVRE_ENABLED=False` até uma configuração própria. Se ativada futuramente, use seu domínio de callback, outro identificador de instalação, outra chave, o vendedor correspondente e preferencialmente uma aplicação Developers própria. Não conectar a mesma conta vendedora nas duas instalações: isso exigiria uma política de distribuição de estoque que não faz parte desta entrega.

A conexão é recusada se vendedor, client ID ou identificador da instalação divergirem da configuração atual. Mesmo desconectando, uma instalação com histórico de outro vendedor não aceita misturar uma nova conta com os anúncios anteriores. Nenhuma migração replica tokens ou dados de uma loja para a outra.

## Ativação futura, somente após autorização de deploy

1. Configurar as variáveis secretas apenas no serviço Django da loja correta; revisar também `ALLOWED_HOSTS`, HTTPS e cookies seguros já existentes.
2. Implantar a versão autorizada. A migração `mercadolivre.0001_initial` apenas cria tabelas; não chama API nem altera peças/vendas. O predeploy existente executa `migrate` e `configurar_operacao`.
3. Entrar como Administrador, abrir Mercado Livre e clicar em Conectar conta. Autorizar o titular do vendedor esperado.
4. Importar lotes manualmente. Conferir título, ID, status e data da consulta antes de vincular cada anúncio à peça correta pelo código.
5. Usar “Anunciar no Mercado Livre” somente para preparar seleções locais. Publicação e sincronização permanecem indisponíveis.

“Desconectar desta loja” remove os tokens locais e invalida tentativas OAuth pendentes, preservando anúncios/vínculos/seleções. Não revoga o grant remotamente: se desejar revogação, faça-a também pela conta Mercado Livre. Essa separação evita uma escrita remota nesta etapa.

## Validação

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py test mercadolivre --settings=pontocar.test_settings --noinput
.venv\Scripts\python.exe manage.py test --settings=pontocar.test_settings --noinput
```

Os testes usam o banco temporário do Django e API simulada: não fazem chamadas ao Mercado Livre nem ao Railway. A homologação real do OAuth depende das credenciais, do cadastro da redirect URI e da futura implantação autorizada.

Resultado local em 16/10/2026: `check` sem problemas, `makemigrations --check --dry-run` sem alterações pendentes e 23 testes da integração aprovados. A suíte completa executou 263 testes: 259 aprovados, dois erros e duas falhas. Os quatro casos abaixo foram repetidos em uma cópia limpa do commit anterior `0778276`, sem a integração, e reproduziram exatamente os mesmos resultados:

- `comercial.tests.ComercialTests.test_pdf_logo_sem_logo_muitas_paginas_termico`: impressão de 58 mm desativada.
- `comercial.tests.ComercialTests.test_pdf_completo_com_oito_itens_cabe_em_uma_folha`: PDF produz duas páginas onde o teste espera uma.
- `estoque.tests.EstoqueTests.test_aplicacao_anterior_preservada`: catálogo sem a chave da marca vazia.
- `contas.tests.ContasTests.test_pix_copia_cola_salvo_e_exibido`: conteúdo PIX de teste recusado pela validação atual.

Essas falhas preexistentes não foram alteradas como parte da integração.

Validação adicional em 16/10/2026: 24 testes da integração aprovados após corrigir a política de referência dos formulários HTTPS. O caso novo confirma o POST com token e referência válidos, a recusa sem referência e a preservação de `no-referrer` no callback OAuth.

Compatibilidade opcional do provedor validada em 16/10/2026: 26 testes aprovados. Foram verificados consentimento por instalação, persistência de escopos, bloqueio ao desativar a opção, recusa de outra conta, de escopos inesperados e de leitura/acesso offline ausentes, além da recusa de métodos de escrita mesmo com a compatibilidade ativada.

## Documentação oficial consultada em 16/10/2026

- [Autenticação e autorização](https://developers.mercadolivre.com.br/autenticacao-e-autorizacao): Authorization Code, PKCE, state, header Bearer, escopos e rotação de refresh tokens.
- [Itens e buscas](https://developers.mercadolivre.com.br/pt_br/itens-e-buscas): busca privada por vendedor, scan/scroll (cinco minutos na API), máximo de 20 no multiget e migração para `/items/bulk` com `status_code` e `body`.

Validação dos escopos funcionais em 16/10/2026: 28 testes da integração aprovados, incluindo persistência de listas longas, recusa de Mercado Pago e outros namespaces e bloqueio ao desativar a compatibilidade.
