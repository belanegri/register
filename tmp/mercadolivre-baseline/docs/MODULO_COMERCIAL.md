# Serviços, orçamentos, OS e cobranças

- Serviços ativos podem ser adicionados ao PDV junto com peças. Quantidade e preço seguem o fluxo existente; serviços nunca alteram estoque.
- Orçamentos e OS ficam em Comercial, acessíveis pelo menu. Seus números derivam da chave sequencial do banco, sem contador em memória.
- Orçamentos, inclusive aprovados, não geram estoque, pagamentos ou contas automaticamente.
- Conversões usam uma tela de confirmação e POST com CSRF. A transação bloqueia o documento e preserva os vínculos; reenvios concorrentes não geram uma segunda venda/OS.
- Na conversão em venda, os itens, cliente e desconto são preservados e a disponibilidade é novamente verificada. O operador escolhe pagamentos ou venda a prazo e precisa de caixa aberto.
- Venda a prazo gera uma única conta a receber por venda, sem lançamento de entrada até o recebimento. Recebimentos parciais/integrais são transacionais, têm chave de idempotência e histórico imutável no PostgreSQL. Cobranças manuais também são permitidas.
- Promissórias existentes continuam no fluxo próprio e não são duplicadas automaticamente como cobranças.
- Contas com recebimentos preservam os registros: cancelamento de venda é bloqueado para exigir conciliação, sem apagar ou estornar silenciosamente valores recebidos. Contas manuais sem recebimento têm cancelamento; para conta originada em venda sem recebimento, use o cancelamento da venda.
- PDFs A4 e 58 mm são gerados com ReportLab. Cabeçalho empresarial vem exclusivamente de ConfiguracaoEmpresa, omite campos vazios e permite ausência de logo. A4 repete cabeçalho/tabelas e paginação; assinatura não sobrepõe os itens. Etiquetas 57 x 30 permanecem intactas.
- Cadastro de veículo no documento descreve o veículo atendido, separado do cadastro existente de veículos de origem de peças.
- Permissões de documentos são operacionais; cadastro de serviços e gestão de cobranças são atribuídos a Administrador/Gerente pelo comando existente configurar_operacao. Permissões personalizadas podem ser atribuídas na administração.

## Validação

118 testes passaram, incluindo os 98 anteriores e 20 novos testes de operações, páginas, PDFs, permissões, recebimentos e concorrência. Django check e makemigrations --check passaram. PDFs de seis páginas foram renderizados e revisados. Formulário a prazo validado em Edge headless.

## Atualização

Código compartilhado; bancos, variáveis e storages independentes. Migrations novas: comercial.0001_initial, comercial.0002_proteger_recebimentos e vendas.0006_itemvenda_servico_alter_itemvenda_peca_and_more. Na PontoCar também entram core.0003 e vendas.0005, ainda não aplicadas na versão anterior; apenas criam configuração empresarial e snapshot opcional para novas vendas, sem preencher ou reescrever dados antigos.
