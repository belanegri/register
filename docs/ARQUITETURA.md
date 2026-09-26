# Arquitetura e limites da etapa inicial

> Registro da etapa inicial. Os módulos operacionais foram implementados posteriormente; consulte `OPERACAO.md` e `RELATORIO_MODULOS_OPERACIONAIS.md` para o estado atual.

## Domínios

- `accounts.User`: extensão de AbstractUser estabelecida antes da primeira migration. Grupos são a fonte única das permissões; não há um campo de cargo paralelo que possa ficar inconsistente.
- `veiculos.Veiculo`: identificação interna, marca/modelo/versão, anos, características, entrada, observações e situação. Uma origem pode ter várias peças. Exclusão protegida enquanto houver peças vinculadas.
- `estoque.Categoria`: cadastro livre, descrição e ativação; nomes únicos.
- `estoque.Localizacao`: código único, nome e superior opcional; profundidade livre, proteção contra ciclos nos formulários do Admin e contra autorreferência no banco. Escritas futuras fora do Admin devem executar `full_clean()` e manter a validação da hierarquia.
- `estoque.Peca`: origem e localização opcionais; categoria obrigatória; código único e UUID permanente, aplicação, anos, motor, posição, condição, custo, preço, quantidade, observações e status.
- `estoque.FotoPeca`: várias imagens por peça com ordem, legenda e caminho baseado em UUID, compatível com troca futura do storage.
- `core.TimestampedModel`: datas de criação e atualização compartilhadas. Não é uma tabela própria.

## Semântica de estoque

Quantidade representa saldo atual. Disponível/reservada exige saldo positivo; vendida exige saldo zero. Baixada pode manter uma quantidade para indicar unidades fisicamente presentes, mas indisponíveis. O status é do cadastro inteiro: reserva parcial exige evolução futura do domínio.

Preço/custo negativos, intervalos de aplicação invertidos e anos fora de 1900–2100 são rejeitados. Campos opcionais usam `blank`; anos ausentes usam NULL. Campos de texto opcionais usam string vazia.

O Admin chama validação de model. O ORM não chama `full_clean()` automaticamente; serviços futuros precisam validar e usar transações. As restrições essenciais de valores/saldos/anos também estão no banco.

## Pesquisa

Busca simples, com AND entre palavras e OR entre os campos relevantes. Ano numérico pode coincidir com intervalo de aplicação ou ano do veículo. A consulta usa `select_related` e paginação de 20 registros. Não há IA, tolerância a erros, normalização de acentos ou sinônimos. Índices comuns ajudam códigos, filtros e igualdade; buscas `icontains` amplas ainda não têm índice especializado. PostgreSQL full-text/trigram deve ser avaliado com volume e termos reais, sem complexidade prematura.

## Segurança e auditoria

Login obrigatório, permissões no servidor, CSRF, escaping dos templates, logout por POST, validadores de senha e cookies com opções seguras. Em `DEBUG=False`, HTTPS e cookies Secure são padrão. Não se confia automaticamente em cabeçalhos de proxy: isso será definido junto ao deploy.

O histórico nativo do Admin registra autor, horário, objeto, inclusão, alteração e exclusão. Ele não registra snapshots completos de antes/depois, nem alterações externas ao Admin; não substitui uma trilha de auditoria de negócio. Não há modelos financeiros nem exclusão de registros financeiros implementados nesta etapa.

## Próximas etapas (não implementadas)

- Clientes: nome obrigatório e documento, contatos, endereço e observações opcionais; histórico via relação com vendas.
- Vendas: rascunho/carrinho, itens com descrição e preço históricos, descontos explícitos, cliente opcional, vendedor individual, pagamentos em tabela própria para permitir divisão futura. Formas de pagamento serão cadastros, não enumeração fixa.
- Finalização: serviço transacional com bloqueio das peças (`select_for_update`), validação de saldo, idempotência, cálculo Decimal e baixa única.
- Cancelamento/devolução: eventos de compensação, motivo, operador e vínculos com a venda original. Não apagar venda, item, pagamento ou movimento confirmado.
- Caixa: sessão por operador, abertura, movimentações, fechamento, saldo esperado/informado e diferença. Suprimento, sangria, recebimento e estorno como eventos auditáveis. Regras de dinheiro versus outros meios serão explícitas.
- Auditoria: evento append-only com ator, operação, instante, motivo e valores antes/depois. Auditoria e transação de negócio devem ser atômicas.
- Dashboard comercial e relatórios: derivados de vendas e movimentos confirmados; não são simulados no painel atual.

## PWA e produção

O layout possui viewport, cor de tema, componentes reutilizáveis e assets locais. Ainda não há manifesto, ícones, service worker, cache offline ou sincronização. Não inventar um logotipo. Não armazenar páginas autenticadas/financeiras em cache indiscriminadamente ao implementar PWA.

`DATABASE_URL`, `SECRET_KEY`, hosts e CSRF ficam no ambiente. WSGI/ASGI e WhiteNoise estão disponíveis. Fotos usam a abstração `STORAGES` para futura configuração S3/Cloudflare R2. Railway, domínio, proxy, storage externo e publicação serão tratados somente quando autorizados. Em produção, usar usuário PostgreSQL sem CREATEDB, backups testados, DEBUG=False e servidor apropriado em vez de runserver.
