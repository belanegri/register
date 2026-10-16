# Loja 2 — publicação concluída

Data: 30/09/2026. Código e23b413, branch codex/instalacoes-independentes.
Deploy: 5c5f98a5-3c5e-4a98-acef-cfa0b189e624, SUCCESS.
URL: https://register-loja-2-production.up.railway.app/
Login: https://register-loja-2-production.up.railway.app/conta/entrar/ — HTTP 200.

## Isolamento confirmado
- Projeto d4ac502c-7bf0-4112-9a30-676a1168b148; ambiente 9d6bafc8-6eef-4d1d-8ce5-90afe643bb74.
- Serviço web 5dee3a98-a5b8-4e48-a953-15942458ccef.
- PostgreSQL novo f0d48663-81db-4da1-aa32-87bab289723a.
- DATABASE_URL da aplicação comparada privadamente: igual à DATABASE_URL desse PostgreSQL novo, no projeto Loja 2.
- Bucket exclusivo 3abaa0b9-37f5-44e5-8a8f-89dac676c0aa; credenciais comparadas com as emitidas para esse bucket.
- Nenhuma operação de publicação, migrations, alteração de variáveis, reinício ou alteração de domínio foi realizada na PontoCar nesta execução.

## Documentos
LEGACY_PONTOCAR_DOCUMENTS=False configurado somente na Loja 2.
Novas vendas gravam empresa_emissao com os dados empresariais do momento da venda. O banco impede alterações posteriores desse campo. Recibos leem essa cópia; mudar ConfiguracaoEmpresa não muda os recibos antigos. Registros antigos não receberam preenchimento em massa.
Instalações legadas mantêm a identificação antiga quando empresa_emissao é NULL; essa compatibilidade está desativada na Loja 2.
Relatórios de estoque e contas gerados na Loja 2 usam ConfiguracaoEmpresa; sem dados, mostram REGISTER — empresa não configurada.
Promissórias sugerem os dados cadastrados para novas emissões e continuam imprimindo os dados armazenados na nota. Não houve alteração de notas existentes.
Não restam referências visuais fixas à PontoCar nas telas/documentos usados pela Loja 2. Os nomes técnicos internos continuam intactos.

## Build e migrations
Dockerfile confirmado nos metadados do deploy; uma réplica; Gunicorn com um worker e duas threads.
Pré-deploy: python manage.py migrate --noinput && python manage.py configurar_operacao.
Start: gunicorn pontocar.wsgi:application --config gunicorn.conf.py.
Todas as migrations aplicadas do zero, com OK nos logs, incluindo core.0003_configuracao_empresa e vendas.0005_venda_empresa_emissao. Nenhum dump/restauração foi utilizado.

## Verificação
98 testes locais aprovados; check e makemigrations --check sem erros.
Django check remoto na Loja 2: sem problemas.
Login e Admin respondem HTTP 200. Rotas de estoque, clientes, vendas, caixa, contas e configuração redirecionam corretamente para login quando não autenticadas. O conteúdo autenticado foi verificado pela suíte local; login real depende da criação do administrador.

## Entrar pela primeira vez
Nenhum administrador foi inventado ou copiado. Execute, em PowerShell interativo na pasta do projeto:

```powershell
.\scripts\criar_admin_loja2.ps1
```

O script usa IDs explícitos apenas da Loja 2 e pede usuário, e-mail e senha pelo terminal. A conexão SSH foi validada com manage.py check.
Alternativa com Railway CLI instalado:

```powershell
railway ssh --project d4ac502c-7bf0-4112-9a30-676a1168b148 --service 5dee3a98-a5b8-4e48-a953-15942458ccef --environment 9d6bafc8-6eef-4d1d-8ce5-90afe643bb74 -- python manage.py createsuperuser
```

Depois acessar /conta/entrar/ e cadastrar os dados reais em /configuracoes/empresa/. Não enviar senha pelo chat.
