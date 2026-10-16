# Relatório — primeira etapa PontoCar

Concluído em 25/09/2026. O sistema foi iniciado e validado em http://127.0.0.1:8000/. Acesso administrativo em http://127.0.0.1:8000/admin/.

## Ambiente verificado antes da instalação

A pasta de trabalho estava vazia; nenhum projeto existente foi sobrescrito. Foram encontrados Python 3.14.7, Python 3.13.15 e uv. Não havia PostgreSQL no PATH, serviço PostgreSQL ou instalação no diretório padrão verificado. Foi escolhido Python 3.13.15 em ambiente virtual isolado.

## Estrutura e apps

Criados `pontocar`, `accounts`, `dashboard`, `veiculos`, `estoque`, `clientes`, `vendas`, `caixa` e `core`, além de `templates`, `static`, `scripts` e `docs`. A árvore detalhada e instruções estão no README.

`clientes`, `vendas` e `caixa` são apenas módulos reservados, sem tabelas, telas ou operações. Nenhuma funcionalidade de PDV, caixa ou relatórios foi desenvolvida.

## Models

| Model | Finalidade |
| --- | --- |
| accounts.User | Usuário próprio baseado em AbstractUser |
| veiculos.Veiculo | Identificação, características, entrada e situação do veículo de origem |
| estoque.Categoria | Categorias cadastráveis e ativação |
| estoque.Localizacao | Hierarquia livre de localização com código único |
| estoque.Peca | Aplicação, origem, categoria, posição, condição, valores, saldo, status e UUID |
| estoque.FotoPeca | Fotos múltiplas, legenda e ordem |
| core.TimestampedModel | Base abstrata de datas; não cria tabela |

Categorias, localizações e veículos referenciados por peças têm exclusão protegida. Valores, anos e consistência de saldo possuem constraints PostgreSQL. UUID prepara referências futuras para etiquetas e QR Code, cuja geração ainda não foi implementada.

## Migrations executadas

21 migrations aplicadas com sucesso:

- `accounts.0001_initial`
- `veiculos.0001_initial`
- `estoque.0001_initial`
- Django: 2 de contenttypes, 12 de auth, 3 de admin e 1 de sessions.

`showmigrations --plan` confirmou todas aplicadas; `makemigrations --check --dry-run` retornou `No changes detected`.

## Dependências instaladas

No ambiente `.venv`, sem instalação global:

| Pacote | Versão |
| --- | --- |
| Django | 5.2.17 |
| django-environ | 0.13.0 |
| psycopg / psycopg-binary | 3.3.6 |
| Pillow | 12.3.0 |
| WhiteNoise | 6.12.0 |
| asgiref | 3.12.1 |
| sqlparse | 0.6.0 |
| tzdata | 2026.4 |

Bootstrap 5.3.8 foi salvo em `static/vendor`, com licença e sourcemaps. `requirements.lock` registra as versões exatas para reprodução.

## Banco

PostgreSQL 17.11 portátil, obtido a partir dos [binários oficiais disponibilizados pela EDB](https://www.enterprisedb.com/download-postgresql-binaries), conforme a opção de distribuição citada pelo [PostgreSQL para Windows](https://www.postgresql.org/download/windows/).

Host `127.0.0.1`, porta `5433`, banco `pontocar`, usuário da aplicação `pontocar`, UTF-8 e autenticação SCRAM-SHA-256. O banco só escuta no loopback. Não foi registrado serviço do Windows. Os binários e dados estão em `.local`, ignorado pelo Git.

Credenciais foram geradas aleatoriamente e gravadas em `.env` e no arquivo local de manutenção; nenhuma senha consta no código versionável. O usuário de aplicação não é superusuário e possui CREATEDB exclusivamente para o banco temporário de testes. Não houve uso de SQLite.

## Comandos utilizados

```powershell
python --version
py --list-paths
Get-Command python,py,psql,pg_ctl -ErrorAction SilentlyContinue
Get-Service -Name '*postgres*' -ErrorAction SilentlyContinue
Get-ChildItem -Force
uv --cache-dir .cache/uv venv --python 3.13 .venv
uv --cache-dir .cache/uv pip install --python .venv/Scripts/python.exe -r requirements.txt
uv --cache-dir .cache/uv pip freeze --python .venv/Scripts/python.exe
.local/pgsql/bin/postgres.exe --version
.venv/Scripts/python.exe scripts/preparar_local.py
.venv/Scripts/python.exe manage.py makemigrations accounts veiculos estoque
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py configurar_grupos
.venv/Scripts/python.exe manage.py criar_admin_local
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py test --settings=pontocar.test_settings --verbosity 1
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
.venv/Scripts/python.exe manage.py showmigrations --plan
.venv/Scripts/python.exe manage.py collectstatic --noinput
.venv/Scripts/python.exe manage.py check --deploy
.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

O ambiente virtual foi criado com o caminho completo do Python 3.13.15 disponível na máquina. Downloads foram feitos com `curl.exe`, e o arquivo do PostgreSQL foi extraído com `zipfile`. A inicialização usou `initdb` e `pg_ctl`; papel/banco foram criados por psycopg. Após corrigir um bloqueio de pipe, a configuração do papel e `.env` foi concluída sem reinicializar o cluster. O servidor Django foi deixado em processo oculto, com logs em `.local/django.log` e `.local/django-error.log`.

## Como iniciar e entrar

```powershell
.\scripts\iniciar.ps1
```

Acesse http://127.0.0.1:8000/. Usuário: `admin`. Senha inicial: consultar `.local/ACESSO_LOCAL.txt`. Troca de senha disponível pelo nome do usuário na barra superior. Para criar funcionários, use o Admin, com contas individuais e atribuição de grupo. Para permitir cadastro pelo Admin, marque também acesso à equipe (`is_staff`).

## O que funciona

- Login, logout via POST e alteração de senha.
- Grupos Administrador, Gerente, Caixa e Vendedor, com permissões iniciais.
- Layout com sidebar desktop, menu móvel, navbar e mensagens reutilizáveis.
- Cadastros de veículos, categorias, localizações, peças e fotos pelo Django Admin.
- Busca simples combinando palavras e anos de aplicação, filtro de status e paginação.
- Painel leve com unidades disponíveis/reservadas e cadastros recentes.
- Histórico nativo de alterações do Admin com identificação do autor.
- Configuração PostgreSQL e secrets por ambiente; arquivos sensíveis ignorados.

## Verificações realizadas

12 testes passaram em PostgreSQL, cobrindo busca composta e intervalo de anos, acesso/permissões, validações, constraints de preço/saldo, proteção de vínculos, ciclos em localizações, indicadores, preservação de grupos, logout por POST, CSRF e abertura/cadastro pelo Admin com registro do autor.

O comando `check` retornou zero problemas. `collectstatic` concluiu após incluir os sourcemaps do Bootstrap. O login foi exercitado no navegador. A interface foi inspecionada em desktop de 1366 px e celular de 390 px, sem overflow horizontal, com abertura e navegação do menu móvel.

Com DEBUG=False, `check --deploy` apresentou somente os avisos de HSTS para subdomínios e preload (W005/W021). Esses recursos dependem do domínio e de HTTPS em todos os subdomínios e não foram habilitados antecipadamente. Com DEBUG=True, os avisos adicionais de configuração local são esperados; o projeto não foi publicado.

## Erros encontrados e correções

1. Cache padrão do uv sem permissão de escrita: redirecionado para `.cache/uv` dentro do projeto.
2. Downloads bloqueados pela rede restrita: downloads oficiais executados com a permissão de rede necessária.
3. `initdb` encontrou restrição do token Windows e, fora dela, erro UTF-8 no caminho acentuado: execução autorizada e caminho curto Windows para o bootstrap.
4. Captura de saída do `pg_ctl` mantinha o inicializador aguardando pipe herdado: o banco já estava ativo; o script de espera foi encerrado e a saída de `pg_ctl` foi alterada para arquivo.
5. Testes iniciais dependiam de manifesto estático ainda não produzido: configuração específica de testes com storage simples; build de estáticos verificado separadamente.
6. `collectstatic` não encontrava sourcemaps do Bootstrap: arquivos oficiais incluídos.
7. Backdrop do menu móvel sobrepunha a sidebar: z-index corrigido e interação verificada no navegador.

## Não implementado e limites

PDV, carrinho, vendas, clientes, pagamentos, caixa, relatórios, devoluções, reserva parcial, auditoria completa de domínio, QR/barcode, PWA/offline, R2 e deploy Railway permanecem futuros. O histórico do Admin não é auditoria completa de antes/depois. Não foram inseridos dados comerciais fictícios.

O PostgreSQL está na pasta solicitada, que pertence ao OneDrive. Para operação contínua, a pasta de dados deve ficar fora da sincronização; não tratar cópia dos arquivos do cluster ativo como backup. Esse projeto é uma base local de desenvolvimento, não uma instalação de produção. Decisões futuras de domínio e produção estão documentadas em `ARQUITETURA.md`.
