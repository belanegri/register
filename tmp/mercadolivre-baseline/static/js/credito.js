document.addEventListener('DOMContentLoaded', () => {
  const campo = document.querySelector('[name="a_prazo"]');
  if (!campo) return;
  const form = campo.closest('form');
  function atualizar() {
    form.querySelectorAll('select[name^="pag-"], input[name^="pag-"][name$="-valor"]').forEach(el => { el.disabled = campo.checked; });
    const vencimento = form.querySelector('[name="vencimento_conta"]');
    if (vencimento) vencimento.required = campo.checked;
    const cliente = form.querySelector('select[name="cliente"]');
    if (cliente) cliente.required = campo.checked;
  }
  campo.addEventListener('change', atualizar);
  atualizar();
});
