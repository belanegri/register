document.addEventListener("DOMContentLoaded", () => {
  const botao = document.getElementById("imprimir");
  const status = document.getElementById("impressao-status");
  const seletor = document.getElementById('impressora-etiqueta');
  const atualizar = document.getElementById('atualizar-impressoras');
  const chave = 'register.impressora.etiquetas.v2';
  let conectado = false, antigo = false, preferida = '';
  try { preferida = localStorage.getItem(chave) || ''; } catch (_) {}
  async function carregarImpressoras() {
    status.textContent = 'Consultando as impressoras… Permita o acesso ao computador se solicitado.';
    const resposta = await fetch('http://127.0.0.1:17857/status', {credentials:'omit', signal:AbortSignal.timeout(10000)});
    const resultado = await resposta.json();
    if (!resposta.ok || resultado.assistente !== 'REGISTER') throw new Error(resultado.erro || 'Assistente indisponível.');
    conectado = true;
    antigo = !Array.isArray(resultado.impressoras);
    if (antigo) {
      status.textContent = 'Assistente antigo: a impressora atual funciona. Instale a atualização para escolher outras impressoras.';
      return;
    }
    seletor.replaceChildren(new Option('Selecione a impressora POS-58', ''));
    resultado.impressoras.forEach(nome => seletor.add(new Option(nome, nome)));
    seletor.value = resultado.impressoras.includes(preferida) ? preferida : resultado.impressoras.includes(resultado.impressora) ? resultado.impressora : '';
    status.textContent = resultado.impressoras.length ? 'Escolha uma POS-58 local ou compartilhada instalada no Windows.' : 'Nenhuma impressora instalada. Instale a POS-58 no Windows e atualize a lista.';
  }
  atualizar.addEventListener('click', async () => {
    atualizar.disabled = true;
    try { await carregarImpressoras(); } catch (_) { conectado = false; status.textContent = 'Baixe e instale o assistente neste computador; permita o acesso local no navegador e atualize a lista.'; }
    finally { atualizar.disabled = false; }
  });
  seletor.addEventListener('change', () => {
    preferida = seletor.value;
    try { localStorage.setItem(chave, preferida); } catch (_) {}
  });
  let pedido = null;
  botao.addEventListener("click", async () => {
    botao.disabled = true;
    status.textContent = "Conectando à POS-58… Se o navegador pedir acesso ao computador, clique em Permitir.";
    pedido ||= crypto.randomUUID();
    try {
      if (!conectado) await carregarImpressoras();
      if (!antigo && !seletor.value) throw new Error('Selecione a impressora de etiquetas antes de imprimir.');
      const dados = {pdf:botao.dataset.etiqueta, pedido};
      if (!antigo) dados.impressora = seletor.value;
      const resposta = await fetch("http://127.0.0.1:17857/imprimir", {
        method: "POST",
        mode: "cors",
        credentials: "omit",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(dados),
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
        ? "Sem confirmação do assistente REGISTER. Verifique a instalação e o acesso local. Tente novamente na mesma impressora para consultar este pedido sem duplicar."
        : `Não foi possível imprimir: ${erro.message}`;
    } finally {
      botao.disabled = false;
    }
  });
  const codigo = document.querySelector(".etiqueta-codigo");
  function ajustarCodigo() {
    let tamanho = 7.5;
    codigo.style.fontSize = `${tamanho}pt`;
    while (codigo.scrollWidth > codigo.clientWidth && tamanho > 5) {
      tamanho -= 0.25;
      codigo.style.fontSize = `${tamanho}pt`;
    }
  }
  document.fonts.ready.then(ajustarCodigo);
  window.addEventListener("beforeprint", ajustarCodigo);
});
