document.addEventListener("DOMContentLoaded", () => {
  const papel = document.getElementById("papel");
  const estilo = document.createElement("style");
  document.head.appendChild(estilo);
  function dimensionar() {
    // Altura real em CSS pixels: 96 px = 25,4 mm, mais as margens do papel.
    const altura = Math.max(30, Math.ceil(papel.getBoundingClientRect().height * 25.4 / 96 + 8));
    estilo.textContent = `@page { size: 58mm ${altura}mm; margin: 3mm; }`;
  }
  window.addEventListener("beforeprint", dimensionar);
  document.getElementById("imprimir").addEventListener("click", async () => {
    await document.fonts.ready;
    const imagens = [...papel.querySelectorAll("img")];
    try { await Promise.all(imagens.map(img => img.decode())); }
    catch { window.alert("Não foi possível carregar a imagem da etiqueta. Atualize a página antes de imprimir."); return; }
    dimensionar();
    window.print();
  });
});
