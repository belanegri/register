# PontoCar Comércio de Peças

Sistema local de estoque, clientes, PDV, vendas, caixa e relatórios. Python, Django Templates, PostgreSQL e Bootstrap 5. Sem frontend SPA, SQLite ou deploy configurado.

**Guia atual:** [Operação do sistema](docs/OPERACAO.md). [Relatório da atualização](docs/RELATORIO_MODULOS_OPERACIONAIS.md).

## Iniciar nesta máquina

Na pasta do projeto, abra PowerShell e execute:

```powershell
.\scripts\iniciar.ps1
```

Se a política local impedir scripts, use apenas para esse processo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\iniciar.ps1
```

Abra http://127.0.0.1:8000/ ou http://127.0.0.1:8000/admin/.

Usuário inicial: `admin`. A senha aleatória está em `.local/ACESSO_LOCAL.txt`, ignorado pelo Git. Altere-a em `/conta/senha/` depois de entrar. O usuário é um superusuário de desenvolvimento, não uma conta compartilhada de funcionários.

Encerre o servidor com Ctrl+C. Para parar o banco, execute `scripts/parar_banco.ps1`. O PostgreSQL portátil não foi instalado como serviço e precisa iniciar novamente após reiniciar o computador; `iniciar.ps1` cuida disso. Se a porta 8000 já estiver ocupada pelo servidor iniciado durante a implementação, use esse servidor ou encerre-o antes de iniciar outro.

## Estrutura

```text
pontocar/           settings, URLs, ASGI, WSGI e configuração de testes
accounts/           usuário próprio, autenticação e grupos
dashboard/          painel inicial de estoque
veiculos/           veículos de origem, Admin e migration
estoque/            categorias, localizações, peças, fotos, busca e testes
clientes/           cadastro, contatos e histórico de compras
vendas/             PDV, vendas, pagamentos, devoluções e relatórios
caixa/              sessões e movimentações de caixa
core/               model abstrato com datas de criação e atualização
templates/          base, componentes, autenticação, painel e estoque
static/css/         identidade visual e responsividade
static/vendor/      Bootstrap 5.3.8, sourcemaps e licença MIT
scripts/            preparação, início e encerramento do PostgreSQL local
docs/               arquitetura e relatório desta etapa
.env.example        exemplo sem credenciais reais
requirements.txt    intervalos de versões
requirements.lock   versões exatas instaladas
.local/             PostgreSQL, cluster, logs e acesso local (ignorado)
.venv/              ambiente virtual isolado (ignorado)
media/              fotos locais (ignorado; criado após upload)
staticfiles/        estáticos processados (ignorado)
```

## PostgreSQL local

- PostgreSQL 17.11, binários oficiais da EDB em `.local/pgsql`.
- Host `127.0.0.1`, porta `5433`, banco `pontocar`, papel `pontocar`.
- UTF-8, autenticação SCRAM-SHA-256, acesso somente por loopback.
- Senha do aplicativo em `.env`; credencial de manutenção em `.local/postgres-admin.json`.
- O papel do aplicativo não é superusuário. Possui CREATEDB **somente no desenvolvimento**, para criar `test_pontocar` durante testes. Não conceder CREATEDB ao usuário de produção.
- O cluster está em `.local/pgdata`; não copie/sincronize esses arquivos enquanto o banco estiver ativo. Como o projeto está no OneDrive, prefira no uso contínuo um PostgreSQL instalado com dados fora de pastas sincronizadas. Backup consistente deve ser feito com `pg_dump`, não por cópia do cluster em execução.

Para usar outro PostgreSQL local, crie um usuário e um banco UTF-8, copie `.env.example` para `.env` e configure `DATABASE_URL` com a senha escolhida. Gere `SECRET_KEY` aleatória. O projeto rejeita engines diferentes de PostgreSQL. Execute as migrations após configurar o banco.

`scripts/preparar_local.py` serve apenas para uma instalação nova com binários previamente extraídos. Ele preserva `.env` e clusters existentes. Não o execute para reiniciar o banco.

## Instalação reprodutível

```powershell
uv --cache-dir .cache/uv venv --python 3.13 .venv
uv --cache-dir .cache/uv pip install --python .venv/Scripts/python.exe -r requirements.lock
# Configure PostgreSQL e .env antes dos comandos seguintes.
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py configurar_operacao
.venv/Scripts/python.exe manage.py createsuperuser
.venv/Scripts/python.exe manage.py collectstatic --noinput
.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
```

Não é necessário ativar o ambiente virtual para usar esses comandos. `criar_admin_local` é uma alternativa de desenvolvimento ao `createsuperuser`, gera senha aleatória e preserva contas já existentes.

## Fluxo de uso inicial

1. Entre no sistema e acesse Administração.
2. Cadastre categorias conforme a necessidade da loja.
3. Cadastre localizações; o campo superior permite setor → estante → prateleira ou outra hierarquia.
4. Cadastre veículos de origem, quando conhecidos.
5. Cadastre peças e suas fotos no Admin; cada peça pode ter várias fotos de até 5 MB cada.
6. Use Estoque de peças para buscar e filtrar por disponibilidade.

Não foram inseridos veículos, categorias ou peças fictícias. A tela inicial vazia reflete os dados reais do banco.

## Permissões

`User` deriva de `AbstractUser`; os papéis usam grupos e permissões nativas do Django.

| Grupo | Permissões iniciais |
| --- | --- |
| Administrador | Todas as permissões existentes na execução inicial do comando |
| Gerente | Ver, cadastrar e alterar estoque e veículos; sem exclusão |
| Caixa | Apenas consulta ao estoque e veículos |
| Vendedor | Apenas consulta ao estoque e veículos |

Grupos existentes não são sobrescritos pelo comando. Novas permissões adicionadas em etapas futuras precisam ser atribuídas explicitamente. O acesso ao Admin também exige `is_staff`; atribuir um grupo não marca essa opção automaticamente. Não dê permissão de alteração de usuários a pessoas que não devam administrar o acesso.

## Verificação

```powershell
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
.venv/Scripts/python.exe manage.py test --settings=pontocar.test_settings
.venv/Scripts/python.exe manage.py collectstatic --noinput
```

Os testes usam PostgreSQL real e um banco temporário separado, nunca SQLite. A configuração de testes armazena uploads em memória e dispensa o manifesto de estáticos. O processamento dos estáticos é verificado separadamente.

## Módulos atuais e próximas integrações

PDV, clientes, vendas, pagamentos, caixa, relatórios, cancelamentos, devoluções e auditoria estão implementados. O fluxo e os limites estão em `docs/OPERACAO.md`. Os grupos foram estendidos para a operação; o quadro anterior descreve as permissões iniciais de estoque.

Permanecem futuras a emissão fiscal, integrações bancárias/maquininha, geração de QR Code, reservas parciais, PWA offline e publicação Railway/R2. O comprovante de venda é interno e não fiscal. O sistema registra pagamentos confirmados pelo operador, sem efetuar cobranças externas.

## Hospedagem no Railway

Consulte [RAILWAY.md](RAILWAY.md) para configura��o econ�mica, vari�veis, R2 privado e migra��o com verifica��o dos arquivos.
