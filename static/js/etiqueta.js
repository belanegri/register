document.addEventListener("DOMContentLoaded", () => {
  const caixa = document.getElementById("etiqueta-texto");
  const texto = document.getElementById("etiqueta-conteudo");
  function ajustarTexto() {
    let tamanho = 9;
    caixa.style.fontSize = `${tamanho}px`;
    while (texto.getBoundingClientRect().height > caixa.clientHeight && tamanho > 4) {
      tamanho -= 0.25;
      caixa.style.fontSize = `${tamanho}px`;
    }
  }
  document.fonts.ready.then(ajustarTexto);
  window.addEventListener("beforeprint", ajustarTexto);
  document.getElementById("imprimir").addEventListener("click", async () => {
    await document.fonts.ready;
    try { await document.querySelector(".etiqueta-barras").decode(); }
    catch { window.alert("Não foi possível carregar o código de barras. Atualize a página antes de imprimir."); return; }
    ajustarTexto();
    window.print();
  });
});
