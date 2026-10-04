document.addEventListener("DOMContentLoaded", () => {
  const botao = document.getElementById("imprimir");
  const status = document.getElementById("impressao-status");
  let pedido = null;
  botao.addEventListener("click", async () => {
    botao.disabled = true;
    status.textContent = "Conectando à POS-58… Se o navegador pedir acesso ao computador, clique em Permitir.";
    pedido ||= crypto.randomUUID();
    try {
      const resposta = await fetch("http://127.0.0.1:17857/imprimir", {
        method: "POST",
        mode: "cors",
        credentials: "omit",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pdf: botao.dataset.etiqueta, pedido }),
        signal: AbortSignal.timeout(60000),
      });
      const resultado = await resposta.json();
      if (!resposta.ok || resultado.status !== "enviada") {
        pedido = null;
        throw new Error(resultado.mensagem || resultado.erro || "O assistente não confirmou a impressão.");
      }
      status.textContent = `Etiqueta enviada à ${resultado.impressora}. Trabalho ${resultado.trabalho} · 30 mm.`;
      pedido = null;
    } catch (erro) {
      status.textContent = erro instanceof TypeError || erro.name === "TimeoutError"
        ? "Sem conexão com o assistente REGISTER. Permita o acesso ao computador neste navegador e tente novamente. Nenhuma impressão pelo navegador será iniciada."
        : `Não foi possível imprimir: ${erro.message}`;
    } finally {
      botao.disabled = false;
    }
  });
  const codigo = document.querySelector(".etiqueta-codigo");
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
});
