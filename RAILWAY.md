# REGISTER no Railway com baixo consumo

Preparação concluída; nenhuma conta criada, publicação realizada ou arquivo enviado. O desenvolvimento local mantém `.env`, PostgreSQL e arquivos locais. Não envie `.env`, `.local`, `media` ou backups para o Git/Docker.

## Serviços e custo

Use apenas um serviço Django (Dockerfile, Gunicorn com 1 worker e 2 threads) e um PostgreSQL com volume persistente. Fotos e comprovantes ficam em um bucket privado Cloudflare R2 Standard; PostgreSQL guarda apenas referências. Estáticos são servidos por WhiteNoise. Não são necessários Redis, Celery, cron, worker separado nem volume no Django.

Estimativa inicial: Django 150–300 MB e PostgreSQL 150–300 MB de RAM, ambos continuamente ativos. São estimativas, não medições em produção. US$ 5 mensais é uma meta, não garantia; CPU, banco e uso real podem ultrapassá-la. Confira consumo depois de alguns dias e configure alertas. Um limite rígido de gastos pode interromper o sistema. Não aumente réplicas nem workers sem medir. Suspensão automática do serviço web é opcional e não está ativada; pode causar demora no primeiro acesso.

R2 Standard inclui 10 GB-mês, 1 milhão de operações classe A e 10 milhões classe B por mês; excedentes são cobrados separadamente do Railway. Armazenamento excedente: US$ 0,015/GB-mês. Saída de dados do R2 é gratuita. Não use Infrequent Access para este caso. Fotos comprimidas de 100–250 KB, como exemplo, permitem aproximadamente 40–100 mil fotos em 10 GB; tamanho real varia e comprovantes também ocupam espaço.

Fontes: https://developers.cloudflare.com/r2/pricing/ e https://docs.railway.com/pricing . Consulte os preços no momento da publicação.

## Variáveis do Django no Railway

- SECRET_KEY: segredo novo, longo e aleatório. Guarde com segurança.
- DEBUG: False
- DATABASE_URL: referência privada `${{Postgres.DATABASE_URL}}` (ajuste Postgres para o nome real do serviço).
- ALLOWED_HOSTS: domínio gerado pelo Railway, sem https e sem barra.
- CSRF_TRUSTED_ORIGINS: https:// seguido do mesmo domínio. Separe múltiplas origens com vírgula.
- TRUST_PROXY_HEADERS: True (somente atrás do proxy controlado do Railway).
- STORAGE_MODE: r2
- R2_ACCESS_KEY_ID e R2_SECRET_ACCESS_KEY: credenciais S3 de token limitado ao bucket, com leitura/escrita de objetos.
- R2_BUCKET_NAME: nome do bucket privado.
- R2_ENDPOINT_URL: https://IDENTIFICADOR_DA_CONTA.r2.cloudflarestorage.com
- DB_CONN_MAX_AGE: 60
- PHOTO_MAX_DIMENSION: 1280
- PHOTO_WEBP_QUALITY: 80
- PHOTO_MAX_PIXELS: 24000000

PORT é fornecido pelo Railway. Não coloque credenciais em railway.json. Não publique o bucket nem ative r2.dev. URLs das fotos são assinadas e expiram em uma hora; recarregue a página quando necessário. Comprovantes exigem permissão e recebem link temporário de 60 segundos. Um link assinado permite acesso a quem o tiver até expirar.

## Ordem para migrar os dados existentes

1. Reserve uma janela sem cadastros ou vendas. Faça backup PostgreSQL com pg_dump em formato custom e cópia de `media` e `.local/comprovantes`. Use ferramentas PostgreSQL compatíveis com a versão do servidor. Preserve também a configuração local fora do repositório.
2. Opcionalmente, antes do backup definitivo, execute `python manage.py otimizar_fotos` para simular. Após conferir, `python manage.py otimizar_fotos --executar` converte fotos antigas não-WebP. Esse passo atualiza referências no banco local e preserva originais. Fotos já WebP não são reprocessadas. Faça novo backup do banco depois da conversão.
3. Crie o bucket R2 Standard privado. Na máquina local configure as quatro variáveis R2, mantendo STORAGE_MODE=local. Execute `python manage.py migrar_arquivos_r2` (simulação sem envio) e, após conferir, `python manage.py migrar_arquivos_r2 --executar`. O comando copia somente arquivos referenciados, valida SHA-256, permite repetir e interrompe em conflito, sem sobrescrever ou apagar origens. Execute apenas uma transferência por vez, sem gravações concorrentes.
4. Crie somente PostgreSQL no Railway. Restaure o backup custom com pg_restore no banco de destino vazio, antes de publicar Django. A restauração deve preservar tabelas, sequências, funções e gatilhos; use --no-owner --no-acl para adaptar o proprietário. Não substitua um banco com dados. A conexão externa temporária da importação é diferente da conexão privada usada pelo aplicativo.
5. Publique o serviço web com o Dockerfile e railway.json presentes, configure as variáveis acima. O build coleta estáticos; antes de cada implantação são executados migrate e configurar_operacao. O processo web executa somente Gunicorn. Não use runserver em produção.
6. Confira login, estoque e fotos, venda, recibo, anexos e permissões. Confira também o próximo código automático. Compare quantidades de registros e arquivos; mantenha o original e o backup até validar a migração. Não mantenha duas instalações recebendo vendas simultaneamente.
7. Observe RAM/CPU/custos. Configure backups do PostgreSQL conforme orçamento e retenção; o bucket não substitui backup. Preserve cópias independentes dos documentos importantes.

## Fotos e compatibilidade local

Novos uploads continuam limitados a 5 MB, aceitam somente imagem estática dentro do limite de pixels e são convertidos automaticamente para WebP qualidade 80, até 1280 pixels, sem ampliação e sem metadados EXIF. Uma nova peça exige ao menos uma foto no formulário administrativo; a última não pode ser apagada nesse formulário. Cadastros antigos sem foto permanecem editáveis até sua regularização. A conversão ocorre no processo web, sem serviço adicional.

Para desenvolvimento, mantenha STORAGE_MODE=local e TRUST_PROXY_HEADERS=False. A `.env` atual não foi alterada. Instale `requirements.lock` na virtualenv; use o servidor local habitual. Gunicorn é utilizado somente no Linux de produção.

## Validação e reversão

`python manage.py test --settings=pontocar.test_settings --noinput`

`python manage.py makemigrations --check --dry-run`

O build Docker pode ser validado em uma máquina com Docker: `docker build -t register .`. R2 e Railway precisam ser validados com as credenciais reais antes de liberar o acesso aos usuários. Para voltar ao modo local use o banco e arquivos correspondentes ao mesmo backup, STORAGE_MODE=local. Após vendas em produção, restaure dados atualizados antes de retomar localmente para não perder lançamentos.
