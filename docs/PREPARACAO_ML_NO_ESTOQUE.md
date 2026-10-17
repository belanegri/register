# Preparação do anúncio no cadastro da peça

Implementação local em 17/10/2026, aguardando autorização de implantação.

No cadastro pelo Admin, abra **Preparar anúncio no Mercado Livre (opcional)**. Os mesmos campos estão disponíveis na edição pelo estoque. É possível guardar título, descrição pública, categoria, fabricante, referência, OEM, origem, preço, quantidade, condição, tipo de anúncio, envio, retirada e frete grátis.

Salvar a peça não consulta a API, não cria seleção e não publica. Os campos funcionam também em lojas sem integração conectada. As observações internas não são usadas como descrição pública.

Ao preparar manualmente o anúncio, os dados salvos aparecem como sugestões editáveis. Categoria salva abre diretamente a preparação, com opção de escolher outra. Características comuns são carregadas quando a categoria as aceita; demais exigências continuam sendo preenchidas na preparação. Fotos existentes são pré-selecionadas até o limite da categoria. A quantidade sugerida respeita o saldo atual. Um tipo de anúncio indisponível exige nova escolha.

Dados enviados pelo usuário na revisão prevalecem sobre as sugestões, inclusive campos apagados e opções desmarcadas. A validação e a confirmação individual de publicação continuam obrigatórias. Alterações durante a preparação não são gravadas de volta no cadastro.

Implantação usa a migração aditiva `estoque.0007`, sem novos serviços ou credenciais. Manter integração e publicação desativadas na Loja 2 enquanto não houver conta própria configurada.

Validação: 53 testes aprovados, cobrindo a integração Mercado Livre, preparação no estoque, formulários e alteração de saldo. `makemigrations --check --dry-run` sem mudanças pendentes e verificação do Django sem problemas. API simulada, sem anúncio real criado.
