document.addEventListener("DOMContentLoaded", () => {
  const marca = document.getElementById("id_marca");
  let modelo = document.getElementById(marca?.dataset.modeloCampo || "id_modelo");
  if (!marca || !modelo || !marca.dataset.modelos) return;
  const catalogo = JSON.parse(marca.dataset.modelos);
  function atualizar(preservar) {
    const anterior = preservar ? modelo.value : "";
    const nomes = catalogo[marca.value] || [];
    const livre = marca.value && nomes.length === 0;
    const novo = document.createElement(livre ? "input" : "select");
    novo.id = modelo.id;
    novo.name = modelo.name;
    novo.required = modelo.required;
    novo.setAttribute("aria-describedby", `${modelo.id}_helptext`);
    if (livre) {
      novo.type = "text";
      novo.maxLength = Number(marca.dataset.modeloMaxlength || 120);
      novo.placeholder = "Informe o modelo";
      novo.value = anterior;
    }
    modelo.replaceWith(novo);
    modelo = novo;
    if (livre) return;
    modelo.replaceChildren(new Option(marca.value ? "Selecione o modelo" : "Selecione primeiro a marca", ""));
    for (const nome of nomes) {
      modelo.add(new Option(nome, nome, false, nome === anterior));
    }
  }
  marca.addEventListener("change", () => atualizar(false));
  atualizar(true);
});
