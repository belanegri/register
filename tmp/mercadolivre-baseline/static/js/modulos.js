// Mantem os menus das tabelas dentro da janela, mesmo em listas com rolagem.
document.addEventListener('DOMContentLoaded', () => {
  if (!document.body.classList.contains('module-ui') || !window.bootstrap?.Dropdown) return;
  document.querySelectorAll('.table-responsive [data-bs-toggle="dropdown"]').forEach(botao => {
    bootstrap.Dropdown.getOrCreateInstance(botao, {
      boundary: 'viewport',
      popperConfig: configuracao => ({...configuracao, strategy: 'fixed'}),
    });
  });
});
