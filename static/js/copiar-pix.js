document.addEventListener("DOMContentLoaded", () => {
  const botao = document.getElementById("copiar-pix");
  const campo = document.getElementById("pix-codigo");
  const status = document.getElementById("pix-status");
  if (!botao || !campo) return;
  botao.addEventListener("click", async () => {
    let copiado = false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(campo.value);
        copiado = true;
      }
    } catch (_) { /* Tenta seleção no acesso local por HTTP. */ }
    if (!copiado) {
      campo.focus();
      campo.select();
      campo.setSelectionRange(0, campo.value.length);
      try { copiado = document.execCommand("copy"); } catch (_) {}
    }
    status.textContent = copiado ? "Código copiado. Cole no aplicativo do banco." : "Selecione e copie o código acima manualmente.";
  });
});
