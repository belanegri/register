# Publicação manual de peças no Mercado Livre

Publicada e habilitada na PontoCar após autorização explícita em 16/10/2026. Qualquer nova implantação continua dependendo de autorização do responsável.

## Estado de produção

- Serviço PontoCar `register`: implantação `aa673456-ca50-4cb0-ad66-37a81d0d7a0e`, status `SUCCESS`, código dos commits locais `21bb6cf` e `cb624c7`.
- Implantação direcionada pelo Railway CLI a partir de um pacote limpo, sem `.env`, tokens, fotos, backups ou temporários. **Não houve push para main**; a fonte GitHub compartilhada da Loja 2 não recebeu esse código.
- `MERCADOLIVRE_PUBLISH_ENABLED=True` configurado somente no serviço PontoCar. Migração e permissões aplicadas pelo predeploy.
- Titular salvou pessoalmente a permissão funcional de publicação em Leitura e escrita no Developers. Conta reconectada; token confirmou `publish-sync:/read-write`, com cifra preservada.
- Confirmadas via API real as sugestões de categoria, características e tipos permitidos. Perfil da conta usa User Products.
- Formulário da peça REG000159 aberto e conferido pelo navegador; **nenhum anúncio foi preparado/enviado/criado na ativação**. A primeira publicação real exige revisão e confirmação do usuário.
- Loja 2 permaneceu na implantação anterior `3bae84cc-8a2a-42f5-9ac0-24b18696c584`, com integração e publicação desativadas; sem alteração de variáveis ou reinício.
- Validação adicional: teste do título do painel aprovado após correção; título e formulário finais conferidos em produção.

## Uso

1. Na lista de peças, abra os três pontos e escolha **Anunciar no Mercado Livre**.
2. Clique em **Preparar anúncio desta peça**. Escolha uma das categorias sugeridas ou informe outra categoria final do Mercado Livre.
3. Revise título, preço, quantidade, condição, tipo de anúncio, envio, descrição pública e características da categoria. Selecione as fotos desta peça.
4. Clique em **Validar e revisar anúncio**. A API valida os dados, mas não cria anúncio nessa ação.
5. Na revisão, confira os dados e fotos, marque a confirmação e clique em **Confirmar e publicar esta peça**. Somente este anúncio será criado.
6. Confira o ID e o resultado no painel. Se a descrição falhar após a criação, o sistema preserva o ID e orienta completá-la no Mercado Livre, sem criar outro anúncio.

É preciso acompanhar manualmente vendas e estoque nos dois sistemas. Publicar não reduz estoque nem altera preço local. Não há publicação em massa, scheduler, sincronização, atualização de anúncios existentes ou pausa automática. A lista de seleções é apenas uma lista de acompanhamento; não inicia envios.

## Ativação autorizada da PontoCar

- Manter as credenciais, chave Fernet, ID de instalação, redirect HTTPS e vendedor já configurados.
- Configurar `MERCADOLIVRE_PUBLISH_ENABLED=True` **somente no serviço register da PontoCar**. Default é `False` em cada instalação. Manter `False`/ausente na Loja 2.
- Manter `MERCADOLIVRE_PROVIDER_SCOPE_COMPAT=True` na PontoCar para o formato funcional de escopos do provedor. Essa configuração sozinha não habilita publicação.
- Na aplicação Mercado Livre Developers, habilitar **Leitura e escrita** para a permissão funcional de publicação de anúncios. Não ampliar os demais recursos. Salvar pessoalmente os termos/CAPTCHA, quando exigidos.
- Implantar a versão autorizada. O predeploy existente aplica `mercadolivre.0004_publicacao` e concede `mercadolivre.publicar_peca` apenas ao grupo Administrador. A migração não chama a API nem envia peças.
- Reconectar a conta PontoCar no painel e revisar/aceitar a nova autorização oficial. Com a publicação habilitada, o OAuth solicita `read write offline_access`. A API continua responsável por validar as permissões funcionais efetivamente concedidas.
- Selecionar e revisar uma peça real com o usuário antes da primeira publicação. Os testes automatizados usam API simulada, sem criar anúncio real de teste.

## Proteções

- Novo transporte separado do cliente de importação, limitado a consultas de metadados, `POST /items/validate`, `POST /items` e descrição do item recém-criado. Sem PUT, PATCH, DELETE, pedidos ou alterações de estoque/preços remotos.
- Permissão de publicação separada, CSRF, confirmação por UUID, revisão vinculada ao usuário, à conexão e à peça; validade de 15 minutos. Campos enviados vêm do rascunho no servidor, não do formulário de confirmação.
- Bloqueio de peças reservadas/vendidas/sem saldo, quantidade superior ao estoque, fotos de outras peças, alterações desde a revisão e anúncios vinculados ainda não encerrados.
- Uma tentativa por peça, com reserva transacional antes da chamada externa. Cliques repetidos e tentativa em andamento não criam um segundo envio.
- Timeout, interrupção ou resultado inesperado após iniciar criação exigem conferência/importação manual. Não existe retry automático de criação nem botão para desbloquear estados incertos.
- Uma rejeição explícita permite corrigir e preparar novamente. Tentativas já publicadas ficam bloqueadas para nova publicação.
- Fotos são enviadas por URLs HTTPS geradas pelo storage existente; URLs temporárias não são persistidas no rascunho nem nos eventos de auditoria. Nenhuma credencial nova é necessária.
- Compatibilidade com vendedores User Products: usa `family_name` quando o perfil tem a tag `user_product_seller`; demais vendedores usam `title`.

## Documentação oficial consultada

Validação local em 16/10/2026: 43 testes da integração aprovados, incluindo formulários, confirmação, vínculo do anúncio criado, User Products, fotos de outra peça, estoque insuficiente, revisão expirada, isolamento por usuário/loja, CSRF, duplo envio durante a chamada externa, timeout, rejeição e descrição parcialmente concluída. API simulada; nenhum anúncio real criado. `manage.py check` sem problemas e migrações sem alterações pendentes. A suíte geral possui quatro falhas preexistentes documentadas no relatório da primeira etapa; não foram alteradas nesta implementação.

- [Publicar produtos](https://developers.mercadolivre.com.br/pt_br/autenticacao-e-autorizacao/publicacao-de-produtos)
- [Validador de publicações](https://developers.mercadolivre.com.br/pt_br/tendencias/validador-de-publicacoes)
- [User Products](https://developers.mercadolivre.com.br/pt_br/user-products)
- [Categorização de produtos](https://developers.mercadolivre.com.br/pt_br/categorizacao-de-produtos)
- [Tipos de publicação](https://developers.mercadolivre.com.br/pt_br/tutorial-tipos-de-publicacao-y-atualizacao-de-artigos)
- [Descrição de produtos](https://developers.mercadolivre.com.br/pt_br/descricao-de-produtos)
