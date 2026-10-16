# PontoCar — guia dos módulos operacionais

Atualização de 25/09/2026. Os módulos inicialmente reservados agora estão implementados localmente. Os documentos da primeira etapa são registros históricos; este guia descreve a operação atual.

## Começar a vender

1. Inicie o projeto com `scripts/iniciar.ps1` e acesse http://127.0.0.1:8000/.
2. Entre com seu usuário individual. Os usuários existentes `admin` e `Isadora` receberam acesso aos novos módulos por suas permissões/grupos.
3. Em **Meu caixa**, informe o dinheiro físico inicial e clique em **Abrir caixa**.
4. Em **Frente de caixa**, pesquise e adicione peças. Ajuste as quantidades no carrinho.
5. Selecione um cliente ou mantenha **Consumidor não identificado**. Cadastre novos clientes pelo menu **Clientes**.
6. Informe desconto, se seu grupo permitir, e os pagamentos recebidos. Para dividir, clique em **Dividir pagamento**. A interface permite até quatro lançamentos; a camada de validação aceita até oito.
7. Confirme o recebimento e clique em **Finalizar venda**. O sistema grava a venda e baixa o estoque junto com os recebimentos, ou desfaz toda a operação se houver erro.
8. Consulte a venda e seu comprovante interno na página de detalhes.

O carrinho fica na sessão do usuário; sair do sistema descarta a sessão. Adicionar ao carrinho não reserva estoque. A disponibilidade é verificada novamente ao finalizar. Alterações de preço exigem remover e adicionar novamente a peça. Peças reservadas ou baixadas não são vendidas pelo PDV.

## Pagamentos e troco

Dinheiro, PIX, cartão de débito e cartão de crédito estão cadastrados. Administrador/Gerente com acesso à equipe pode criar, renomear e desativar formas no Admin, pelo link **Configurar formas de pagamento** na tela Vendas.

O atributo **movimenta dinheiro físico** determina se o recebimento entra no saldo da gaveta. Essa característica e o nome são copiados para o pagamento da venda, preservando o histórico quando o cadastro é alterado.

Pagamentos devem cobrir o total. Excesso somente é aceito como troco de dinheiro. PIX/cartão não compõem o dinheiro contado no fechamento. O valor lançado como receita considera o troco devolvido.

O sistema registra a informação fornecida pelo operador: **não há integração com adquirente, maquininha, banco, confirmação automática de PIX ou reembolso eletrônico**. Receber/cobrar e devolver valores no meio externo continua sendo uma ação do operador. O comprovante é interno e não fiscal; não emite NF-e/NFC-e.

## Caixa

- Uma sessão aberta por operador; cada sessão recebe código `CX-000001` em diante.
- Abertura registra saldo inicial, usuário e horário.
- Suprimento adiciona dinheiro; sangria retira. Ambos exigem motivo e valor positivo.
- Sangria/reembolso em dinheiro não podem exceder o saldo esperado.
- Os recebimentos, inclusive eletrônicos, aparecem no histórico; a coluna **Dinheiro físico?** indica se compõem o saldo contado.
- O fechamento salva saldo esperado, contado, diferença, observação e instante. Não é possível lançar nova operação em sessão fechada.
- Cancelamento/devolução de uma venda antiga usa o caixa atualmente aberto do operador autorizado, preservando o caixa original.
- Reenvio de uma movimentação manual com a mesma chave não duplica o lançamento.

## Cancelamento e devolução

Abra **Vendas**, selecione a venda e use a operação desejada. Somente Administrador/Gerente têm essas permissões iniciais.

**Cancelar** repõe todos os itens e registra estorno pelos meios originais. Exige motivo e caixa aberto. Uma venda com devolução parcial não pode ser cancelada: devolva os itens restantes. Repetir o cancelamento não repõe estoque duas vezes.

**Devolver item** permite quantidade parcial, motivo e meio de reembolso. O desconto original é rateado em centavos; a última devolução do item absorve eventual resto de arredondamento. O sistema não permite devolver mais que a quantidade vendida. As peças devem ser fisicamente recebidas e conferidas antes da operação. Se a peça voltou sem condições de venda, marque-a como baixada/indisponível no estoque após a conferência.

Vendas, pagamentos, itens, estornos e devoluções permanecem no histórico. Não existe botão para excluir registros financeiros. O banco também bloqueia exclusão de vendas/caixas e alteração/exclusão de eventos, pagamentos, itens, devoluções e movimentos. Uma correção financeira deve ocorrer por compensação, não apagando o passado.

## Clientes, estoque e códigos

Cliente exige somente nome. Documento, telefone, e-mail, endereço e observações são opcionais. Pode ser desativado. Seu histórico mostra apenas vendas que o usuário tem permissão para consultar.

As 36 categorias, catálogo de 338 modelos e opções de marca continuam disponíveis. Peças, veículos e localizações usam códigos automáticos e preservam códigos anteriores. Vendas usam `VEN-000001` e caixas `CX-000001`, derivados das sequências do banco. Numerações são crescentes e podem ter lacunas após transações desfeitas.

Peças e fotos continuam sendo cadastradas pelo Admin. A edição de preço, custo, quantidade e demais campos principais gera evento com valores anteriores/posteriores. Uma tela de edição aberta antes de uma venda não pode sobrescrever a baixa de estoque: o formulário exige recarregar quando identifica uma alteração mais recente. Exclusão de peças foi substituída operacionalmente pela baixa de status; o histórico é preservado.

## Painel e relatórios

O painel mostra vendas do dia, movimento líquido do dia e do mês, quantidade de vendas no mês, últimas vendas e indicadores de estoque. Vendedor/Caixa consultam suas próprias operações; gestores consultam todos os operadores.

Relatórios permitem escolher até 366 dias e exportar CSV. Recebimentos/estornos seguem a data do movimento. A lista de vendas segue a data de criação da venda e sua situação atual. Assim, uma devolução de venda antiga reduz o movimento do período em que ocorreu. Totais por forma mostram pagamentos originais antes dos estornos. O estoque exibido é sempre a posição atual, não uma reconstrução histórica.

## Grupos e permissões

| Grupo | Operação inicial |
| --- | --- |
| Vendedor / Caixa | PDV, próprio caixa, próprias vendas e cadastro/consulta de clientes |
| Gerente | Operação acima, descontos, cancelamento/devolução, relatórios, todos os caixas/vendas e configuração de pagamentos |
| Administrador | Administração dos cadastros, usuários e módulos operacionais |

Grupos se somam: quem pertence a Administrador e Vendedor continua tendo poderes administrativos. O comando `configurar_operacao` adiciona permissões dos novos módulos sem remover permissões existentes. `is_staff` é necessário somente para acessar o Django Admin; PDV, clientes e caixa têm suas próprias telas.

## Auditoria e limites técnicos

Operações relevantes gravam autor, instante, objeto e dados em `core.Evento`, disponível no Admin para gestores. Estornos, devoluções, descontos, abertura/fechamento, movimentações e mudanças do estoque são rastreados. O log é protegido no PostgreSQL. A trilha de alterações feita diretamente no banco por administradores de infraestrutura não faz parte da auditoria da aplicação.

Serviços de venda usam transações e bloqueios de linhas (`select_for_update`), com ordenação das peças. Isso impede vender a mesma última unidade duas vezes. UUIDs de requisição previnem duplicação de finalização/devolução. Valores são tratados com Decimal e rateio exato de centavos.

Continuam para uma futura publicação: Railway, domínio/HTTPS, storage R2, backup operacional, integração fiscal e meios de pagamento externos. PWA permanece preparada pela estrutura responsiva e assets locais; não foi ativado funcionamento offline nem cache de operações financeiras. O PostgreSQL atual é local e está na pasta do projeto no OneDrive; para uso contínuo, migre seus dados para uma pasta fora da sincronização e use backups consistentes.

## Instalar a atualização em outra cópia

```powershell
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py configurar_operacao
.venv/Scripts/python.exe manage.py collectstatic --noinput
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py test --settings=pontocar.test_settings
```

Reinicie o servidor após as alterações. Não foram adicionadas dependências de terceiros.


## Troco, edição e nota promissória

No PDV, selecione **Dinheiro** e informe o valor entregue pelo cliente. O troco aparece automaticamente e considera desconto e pagamento dividido. PIX, cartão e promissória não geram troco. O servidor valida novamente todos os valores ao concluir.

Em **Vendas**, use **Editar**, **Cancelar** ou **Devolver item** (Administrador/Gerente). A edição permite alterar cliente, itens, quantidades, preços, desconto e pagamentos de uma venda concluída sem devoluções. Exige motivo e caixa aberto; cancela a anterior e cria uma venda corrigida ligada ao histórico. Confirme os valores efetivamente recebidos/reembolsados, especialmente ao mudar a forma de pagamento. Se a correção for inválida, a operação inteira é desfeita. A opção de cancelamento atende à remoção operacional da venda, preservando os registros financeiros.

Para vender a prazo, selecione **Nota promissória**. Cadastre e selecione o cliente com CPF/CNPJ e preencha vencimento, beneficiário, local de emissão e local de pagamento; o CPF/CNPJ do beneficiário também pode ser informado. Após concluir, abra **Imprimir promissória 58 mm** na venda. A nota inclui número automático, valor, promessa de pagamento, vencimento, partes, locais, data de emissão e espaço para assinatura. Os campos do documento seguem os elementos do artigo 75 do [Decreto 57.663/1966, Anexo I](https://www.planalto.gov.br/ccivil_03/decreto/1950-1969/anexo/an57663-66.pdf).

A emissão registra um valor a receber; somente **Registrar recebimento** lança entrada no caixa. Permite recebimentos parciais, com saldo atualizado. Vendedor/Caixa acessam apenas suas vendas; gestores acessam todas. Na devolução, primeiro se abate a dívida pendente; somente a diferença já recebida é reembolsada. No cancelamento, o saldo pendente é cancelado e os recebimentos anteriores são estornados. Notas e seus movimentos são protegidos contra alteração/exclusão no banco.

Recibos e promissórias usam papel de 58 mm e área útil de 52 mm. Na impressão, configure papel 58 mm, escala 100% e desative cabeçalhos/rodapés. O comprimento acompanha o conteúdo. A conferência em impressora física depende do equipamento e do driver utilizados.


## Preço negociado e contas a pagar

No carrinho do PDV, altere **Preço unitário nesta venda** e clique em **Aplicar preço**. O total e o troco são recalculados. O preço cadastrado no estoque permanece igual, e a auditoria registra preço de catálogo e preço vendido. A alteração é permitida aos operadores com acesso ao PDV.

Administrador e Gerente acessam **Contas a pagar** no menu: cadastro de descrição, fornecedor, valor e vencimento; filtros de pendentes, vencidas, pagas e canceladas; edição e cancelamento de contas pendentes. **Registrar pagamento** quita o valor integral e registra data, meio e operador. Não efetua transferências nem paga boletos. Pagamentos externos não movimentam o caixa do sistema; retirada em dinheiro exige caixa aberto, data de hoje e saldo suficiente, gerando sangria vinculada à conta. Reenvios não duplicam o pagamento.


## PDFs, comprovantes e links das contas

Na página da conta, **Gerar PDF desta conta** abre um documento A4 para salvar ou imprimir. Na lista, selecione busca, situação, tipo, categoria, forma prevista e período (vencimento, pagamento programado ou realizado) e use **Gerar relatório PDF**. O relatório inclui todas as contas dos filtros, não apenas a página visível, com quantidade e totais por situação. Filtros inválidos impedem a exportação.

O cadastro e a edição têm campos opcionais para comprovante e link. A seção **Comprovantes e links de acesso** permite acrescentar outros documentos, inclusive em contas pagas. Aceita PDF, JPG e PNG de até 10 MB por arquivo e links HTTP/HTTPS. Os PDFs individuais relacionam nomes dos comprovantes e links; não incorporam o conteúdo dos arquivos anexados.

Arquivos ficam em `.local/comprovantes`, fora de `/media/`, com nomes internos aleatórios. Downloads exigem login e permissão de consulta das contas. Inclua essa pasta nos backups, juntamente com o banco. A criação de anexos é auditada. A geração dos PDFs utiliza ReportLab, registrado nos arquivos de dependências.


## Código de barras e leitor USB

As peças novas recebem código REG com seis dígitos (ex.: REG000001), continuando a sequência existente. Códigos antigos, incluindo PC-, são preservados; editar uma peça não muda seu código. A sequência é atômica no PostgreSQL e pode ter intervalos após cadastros cancelados, sem reutilização dos números.

O Code 128 é gerado dinamicamente, sem arquivos de imagem no armazenamento. No cadastro administrativo, aparece após salvar; também aparece nas páginas de visualização e edição da peça.

No PDV, clique em **Ler código de barras** e use um leitor USB em modo teclado, configurado para enviar Enter ao final. Também é possível digitar o código e clicar em Adicionar. Cada leitura adiciona uma unidade, inclusive de códigos antigos. Aguarde a página atualizar antes da próxima leitura. A pesquisa manual continua disponível. A leitura não finaliza a venda nem baixa o estoque: as validações são repetidas ao finalizar.

**Imprimir etiqueta** abre diretamente um PDF de uma página, sem data, título ou endereço do site impressos pelo navegador. Use tamanho real (100%), sem ajustar à página, com papel personalizado de **57 × 30 mm** no driver, escala 100%, margens nenhuma e cabeçalhos/rodapés desativados. A etiqueta começa no topo e tem comprimento fixo, independente dos comprovantes de 58 mm. Contém somente nome da peça, marca, modelo, ano, lado / posição, código da peça e código de barras. Se a prévia mostrar uma bobina longa, ajuste o tamanho no driver; desative avanço extra/corte adicional quando disponível. Teste uma unidade na impressora e leitor antes de imprimir em lote.

Fotos de peças são opcionais: é possível cadastrar sem foto e remover todas as fotos. Imagens enviadas continuam sendo validadas e comprimidas automaticamente.
