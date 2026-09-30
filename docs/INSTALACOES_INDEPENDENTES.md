# REGISTER — instalações independentes

## Arquitetura e estado
O código é compartilhado; banco, usuários, sessões, arquivos, credenciais e configuração empresarial não são compartilhados. Não há seleção de empresa por filtro no mesmo banco.

PontoCar existente:
- Projeto: `6dd910a8-3746-4db8-b50b-4cd05f664ab7`.
- Web: `3a0435fb-2e01-4c74-82fb-ec9d81c297d2`.
- PostgreSQL: `bf9a18fc-fcd1-4dce-816b-348a3844d81d`.
- URL: https://register-production-351c.up.railway.app/
- Banco, domínio, bucket R2, variáveis e serviços não foram alterados nesta etapa.

Loja 2 criada separadamente:
- Projeto: `d4ac502c-7bf0-4112-9a30-676a1168b148` (REGISTER - Loja 2).
- Ambiente: `9d6bafc8-6eef-4d1d-8ce5-90afe643bb74`.
- Web: `5dee3a98-a5b8-4e48-a953-15942458ccef` (register-loja-2), sem deploy e sem fonte conectada.
- PostgreSQL novo: `f0d48663-81db-4da1-aa32-87bab289723a`, online, volume próprio.
- Bucket privado Railway S3: `3abaa0b9-37f5-44e5-8a8f-89dac676c0aa`, register-loja-2; vazio, acesso de leitura validado.
- Domínio reservado: https://register-loja-2-production.up.railway.app/ (aplicação ainda não ativa).
- Nenhum restore, dump, usuário ou arquivo da PontoCar foi enviado para a Loja 2.
- O PostgreSQL novo já consome recursos; a aplicação ainda não tem processo rodando. O bucket vazio não contém arquivos empresariais.

## Identidade visual
REGISTER identifica o software no login, menu, títulos, dashboard, rodapé, PWA e Admin.
O login e a barra superior exibem `Empresa: nome fantasia`, com razão social como alternativa. Sem cadastro, nenhum nome empresarial é inventado. O processador de contexto só lê a configuração do banco da instalação, sem cache global.
A migration core.0003_configuracao_empresa permanece aditiva e sem dados empresariais. Nenhum pacote Python, migration antiga, função SQL ou ID foi renomeado.

## Documentos: bloqueio antes de ativar Loja 2
Não foram alterados os recibos e documentos históricos. Promissórias usam os campos já armazenados nelas.
Ainda há identificação fixa da PontoCar em templates/impressao/recibo.html, templates/vendas/detalhe.html, estoque/pdf.py, contas/pdf.py e no beneficiário inicial de vendas/forms.py.
**Não liberar a Loja 2 para operação antes de resolver essa identidade documental.** Usar dados da configuração atual na reimpressão de documentos antigos mudaria sua identidade retroativamente. Uma etapa posterior deve guardar uma cópia dos dados empresariais em cada documento novo, preservando o tratamento dos registros antigos. O usuário autorizou adiar essa integração quando houver risco.
Etiquetas permanecem no PDF 57 × 30 mm, sem marca empresarial, com lado / posição. Nenhuma regravação de venda, recibo ou promissória foi executada.

## Variáveis separadas
Já configuradas no serviço novo, sem deploy:
- SECRET_KEY: nova chave aleatória exclusiva, não incluída no Git ou no relatório.
- DATABASE_URL: referência `${{Postgres.DATABASE_URL}}` resolvida no projeto Loja 2.
- ALLOWED_HOSTS: register-loja-2-production.up.railway.app.
- CSRF_TRUSTED_ORIGINS: https://register-loja-2-production.up.railway.app.
- DEBUG=False, TRUST_PROXY_HEADERS=True, STORAGE_MODE=r2.
- R2_ENDPOINT_URL, R2_BUCKET_NAME, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY: exclusivamente do bucket novo.
- R2_REGION_NAME: região retornada pelo bucket; default auto preserva o R2 da PontoCar.
- DB_CONN_MAX_AGE=60, PHOTO_MAX_DIMENSION=1280, PHOTO_WEBP_QUALITY=80, PHOTO_MAX_PIXELS=24000000.
Os nomes R2_* são mantidos por compatibilidade; o backend S3 também atende o bucket privado do Railway. Fotos e comprovantes usam prefixos separados dentro do bucket exclusivo da empresa. As imagens não são armazenadas no PostgreSQL.
Em cada instalação, manter HTTPS, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True e SECURE_SSL_REDIRECT=True (defaults em produção). Não configurar domínio de cookies compartilhado.
Para desenvolvimento separado, usar outro checkout, outro .env, outro PostgreSQL e outra pasta media. Nunca copiar .env ou .local da PontoCar para a Loja 2.

## Ativação e código compartilhado
Código preparado na branch codex/instalacoes-independentes. Não publicar main automaticamente antes de preparar a migration da PontoCar.
Após resolver documentos para Loja 2, configurar explicitamente o serviço novo para Dockerfile, uma réplica e os comandos:
- Pré-deploy: `python manage.py migrate --noinput && python manage.py configurar_operacao`.
- Start: `gunicorn pontocar.wsgi:application --config gunicorn.conf.py`.
Não confiar exclusivamente em railway.json, cuja depreciação foi informada pelo CLI.
Conectar o mesmo repositório belanegri/register ao serviço novo, com a versão aprovada. Nenhum arquivo .local, backup ou media deve fazer parte do deploy.
As migrations remotas da Loja 2 ainda não foram executadas. Executar normalmente no banco novo; nunca usar pg_restore nem copiar banco da PontoCar.
Na PontoCar, verificar backup recuperável e executar a migration aditiva antes de ativar o código que consulta ConfiguracaoEmpresa. Não alterar DATABASE_URL, domínio ou storage. A publicação de produção ficou pendente de autorização devido ao risco de interromper páginas se o código entrar antes da tabela nova.

## Administrador e dados empresariais
Não foi criado administrador para a Loja 2 nem definida senha. Após o deploy seguro estar ativo, usar terminal interativo:

```powershell
railway ssh --project d4ac502c-7bf0-4112-9a30-676a1168b148 --service 5dee3a98-a5b8-4e48-a953-15942458ccef --environment 9d6bafc8-6eef-4d1d-8ce5-90afe643bb74 -- python manage.py createsuperuser
```

O comando solicita usuário, e-mail e senha escolhidos pelo responsável. Não usar criar_admin_local em produção; não reutilizar conta da PontoCar.
Depois entrar em /conta/entrar/ e acessar /configuracoes/empresa/. Preencher somente os dados reais da empresa correspondente. A página exige core.change_configuracaoempresa; superusuários têm acesso. configurar_operacao concede permissões ao grupo Administrador de modo aditivo.
Para PontoCar, o mesmo endereço /configuracoes/empresa/ ficará disponível após publicar esta versão e aplicar core.0003. Não importar o cadastro de uma empresa na outra.

## Validação
- Django check: sem problemas.
- makemigrations --check --dry-run: sem mudanças pendentes.
- Suíte completa final: 94 testes passaram (login, configuração, permissões, páginas, estoque, clientes, vendas, caixa, fotos, códigos e PDFs).
- Banco PostgreSQL local novo criado exclusivamente para validação: migrate, configurar_operacao e check concluídos.
- Banco novo contém somente 36 categorias, 338 modelos de veículos e 5 formas de pagamento como dados-base; zero usuários, peças, fotos, clientes, vendas, pagamentos, caixa, contas, promissórias, eventos e configuração empresarial. Grupos e permissões são criados pelos comandos normais.
- Documentos históricos e core.0003 não sofreram alterações nesta etapa.
- Não houve troca de DATABASE_URL nem acesso cruzado entre instalações.

## Próximos passos e autorização
1. Resolver identidade em novos documentos com preservação dos históricos antes de liberar a Loja 2.
2. Autorizar janela/plano de publicação da PontoCar com migration aditiva antes do novo código.
3. Publicar Loja 2, aplicar migrations normais, criar administrador e cadastrar dados reais.
4. Cadastrar empresa PontoCar em sua própria instalação após atualizar.
5. Validar login e operações com contas próprias em cada domínio.
Não há perda de dados, limpeza, renumeração ou cópia de informações empresariais incluída nesse procedimento.
