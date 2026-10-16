# Entrega dos módulos operacionais

Data: 25/09/2026. Escopo autorizado: completar os módulos de operação previstos, mantendo o projeto local e sem publicar no Railway.

## Entregue

- Clientes: cadastro/edição, busca, contatos opcionais, ativação e histórico.
- PDV: busca de estoque, carrinho por sessão, quantidades, cliente, desconto autorizado, pagamento dividido, troco, finalização e baixa atômica do estoque.
- Vendas: códigos automáticos, itens/preços históricos, pagamentos, detalhes, cancelamento, devoluções parciais e histórico.
- Caixa: abertura por operador, recebimentos, suprimento, sangria, estornos, fechamento, saldo esperado/informado e diferença.
- Formas de pagamento cadastráveis, com Dinheiro, PIX, Débito e Crédito como dados iniciais.
- Dashboard comercial e estoque; relatórios por período com exportação CSV.
- Papéis e permissões aplicados aos grupos existentes; telas respeitam acesso por operador.
- Auditoria append-only e bloqueios PostgreSQL de exclusão/alteração de registros históricos.
- Proteção contra estoque insuficiente, reenvio duplicado e edição administrativa desatualizada.

## Modelos e migrations

Novos models: `Cliente`, `FormaPagamento`, `Venda`, `ItemVenda`, `Pagamento`, `Devolucao`, `SessaoCaixa`, `MovimentoCaixa`, `Evento`.

Migrations aplicadas: clientes `0001`, vendas `0001–0002`, caixa `0001–0003`, core `0001–0002`. Os dados anteriores de usuários, peças, marcas e categorias foram preservados. Nenhuma venda fictícia foi gravada no banco operacional pelo processo de teste.

Os campos de código de venda e caixa são derivados dos IDs sequenciais PostgreSQL e não exigem digitação. Fotos permanecem no storage configurado; não houve alteração da infraestrutura.

## Verificações

Resultado final: **46 testes passaram** em PostgreSQL separado; `check` sem problemas e nenhuma migration pendente. A suíte inclui:

- Venda com dinheiro/PIX e troco; desconto e rateio em centavos.
- Reenvio de finalização e devolução sem duplicar efeitos.
- Falha por saldo, preço alterado, peça reservada ou pagamento incorreto com rollback.
- Dois operadores concorrentes vendendo a última unidade: só uma venda é aceita.
- Cancelamento e reposição uma única vez; devolução parcial/total e limite de quantidade.
- Abertura exclusiva, fechamento com diferença e impedimento de operar caixa fechado.
- Estorno de venda anterior lançado em nova sessão sem alterar caixa fechado.
- Bloqueio de alteração/exclusão de histórico pelo banco.
- Permissões nas telas e no Admin, inclusive vendas/caixas de outro operador.
- Cadastro de clientes, histórico de nomes e acesso às páginas de operação.
- Edição antiga de estoque não sobrescreve a baixa de venda.

O teste concorrente inicialmente deixou conexões das threads abertas durante a remoção do banco de teste. Corrigido usando fechamento explícito das conexões de cada thread. Não afetou o banco operacional.

`check`, `makemigrations --check --dry-run` e `collectstatic` foram executados. O PDV foi inspecionado em desktop (1366 px) e celular (390 px), sem rolagem horizontal. Adição ao carrinho, divisão de pagamentos e previsão de troco foram conferidas no navegador, sem finalizar venda real. Os testes não substituem homologação da loja com seus procedimentos reais.

## Uso e limites

Consulte `OPERACAO.md` para o fluxo de uso, papéis, relatórios e limites. O registro financeiro é interno: não há emissão fiscal, cobrança automática de cartão/PIX ou reembolso bancário integrado. Não houve deploy, mudança de firewall ou exposição pública. PWA instalável/offline permanece futura, conforme a preparação prevista inicialmente.
