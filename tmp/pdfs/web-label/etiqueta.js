document.addEventListener("DOMContentLoaded", () => {
  const codigo = document.querySelector(".etiqueta-codigo");
  const barras = document.querySelector(".etiqueta-barras");
  const botao = document.getElementById("imprimir");
  function ajustarCodigo() {
    let tamanho = 9;
    codigo.style.fontSize = `${tamanho}pt`;
    while (codigo.scrollWidth > codigo.clientWidth && tamanho > 5) {
      tamanho -= 0.25;
      codigo.style.fontSize = `${tamanho}pt`;
    }
  }
  document.fonts.ready.then(ajustarCodigo);
  window.addEventListener("beforeprint", ajustarCodigo);
  botao.addEventListener("click", async () => {
    botao.disabled = true;
    try {
      await document.fonts.ready;
      await barras.decode();
      ajustarCodigo();
      window.print();
    } catch {
      window.alert("Não foi possível carregar a etiqueta. Atualize a página antes de imprimir.");
    } finally {
      botao.disabled = false;
    }
  });
});
