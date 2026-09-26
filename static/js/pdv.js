document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("checkout");
  if (!form) return;
  const moeda = new Intl.NumberFormat("pt-BR", {style: "currency", currency: "BRL"});
  const formatar = cents => moeda.format(cents / 100);
  const centavos = value => {
    let texto = String(value || "0").replace(/R\$|\s/g, "");
    if (texto.includes(",")) texto = texto.replace(/\./g, "").replace(",", ".");
    if (!/^\d+(\.\d{0,2})?$/.test(texto)) return NaN;
    const [inteiro, decimal = ""] = texto.split(".");
    return Number(inteiro) * 100 + Number(decimal.padEnd(2, "0"));
  };
  const linhas = [...form.querySelectorAll(".pagamento-linha")];
  const dividir = document.getElementById("dividir-pagamento");
  linhas.forEach((linha, index) => {
    if (index && linha.dataset.erros === "0" && ![...linha.querySelectorAll("input,select")].some(input => input.value)) linha.classList.add("d-none");
  });
  dividir?.addEventListener("click", () => {
    linhas.find(linha => linha.classList.contains("d-none"))?.classList.remove("d-none");
    dividir.hidden = !linhas.some(linha => linha.classList.contains("d-none"));
  });
  function atualizar() {
    let subtotal = centavos(form.dataset.subtotal);
    if (form.dataset.edicao) subtotal = [...form.querySelectorAll(".item-correcao")].reduce((s, linha) => {
      if (linha.querySelector("[name$='-DELETE']").checked || !linha.querySelector("[name$='-peca']").value) return s;
      return s + Number(linha.querySelector("[name$='-quantidade']").value) * centavos(linha.querySelector("[name$='-preco']").value);
    }, 0);
    const total = subtotal - centavos(form.querySelector("[name=desconto]").value);
    let cobertura = 0, dinheiro = 0, promissoria = false;
    linhas.forEach(linha => {
      const select = linha.querySelector("select");
      if (!select.value) return;
      const option = select.selectedOptions[0];
      const valor = centavos(linha.querySelector("[name$='-valor']").value);
      cobertura += valor;
      if (option.dataset.dinheiro === "1") dinheiro += valor;
      if (option.dataset.promissoria === "1") promissoria = true;
    });
    const campos = document.getElementById("dados-promissoria");
    if (campos) campos.hidden = !promissoria && !campos.querySelector(".errorlist");
    document.getElementById("total-previa").textContent = Number.isFinite(total) ? formatar(total) : "Confira os valores";
    const aviso = document.getElementById("pagamento-previa");
    if (!Number.isFinite(total + cobertura) || total < 0) aviso.textContent = "Confira os valores informados.";
    else if (cobertura < total) aviso.textContent = `Falta informar: ${formatar(total - cobertura)}`;
    else if (cobertura > total && cobertura - total >= dinheiro) aviso.textContent = "Valor excedente: ajuste os pagamentos. Troco somente em dinheiro; PIX, cartão e promissória não geram troco.";
    else aviso.textContent = `TROCO: ${formatar(cobertura - total)}`;
  }
  form.addEventListener("input", atualizar);
  form.addEventListener("change", atualizar);
  form.addEventListener("submit", () => { const botao = form.querySelector("button[type=submit], button:not([type])"); if (botao) botao.disabled = true; });
  atualizar();
});
