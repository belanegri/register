document.addEventListener("DOMContentLoaded", () => {
  const marca = document.getElementById("id_marca");
  let modelo = document.getElementById(
    marca?.dataset.modeloCampo || "id_aplicacao"
  );

  if (!marca || !modelo || !marca.dataset.modelos) return;

  const catalogo = JSON.parse(marca.dataset.modelos);

  function criarBotao(campo, tipo) {
    if (document.getElementById(`add-${tipo}`)) return;

    const botao = document.createElement("a");
    botao.id = `add-${tipo}`;
    botao.href = "#";
    botao.className = "related-widget-wrapper-link add-related";
    botao.title =
      tipo === "marca"
        ? "Adicionar nova marca"
        : "Adicionar novo modelo";

    botao.innerHTML = '<span style="font-size:22px;font-weight:bold;">+</span>';

    campo.insertAdjacentElement("afterend", botao);

    botao.addEventListener("click", (event) => {
      event.preventDefault();

      const marcaAtual = marca.value;

      let url = "/admin/veiculos/modeloveiculo/add/?_popup=1";

      if (tipo === "modelo" && marcaAtual) {
        url += `&marca=${encodeURIComponent(marcaAtual)}`;
      }

      window.open(
        url,
        tipo === "marca"
          ? "cadastro_nova_marca"
          : "cadastro_novo_modelo",
        "width=800,height=600,resizable=yes,scrollbars=yes"
      );
    });
  }

  function atualizar(preservar = false) {
    const anterior = preservar ? modelo.value : "";
    const nomes = catalogo[marca.value] || [];
    const livre = marca.value && nomes.length === 0;

    const novo = document.createElement(livre ? "input" : "select");

    novo.id = modelo.id;
    novo.name = modelo.name;
    novo.required = modelo.required;
    novo.className = modelo.className;

    novo.setAttribute(
      "aria-describedby",
      `${modelo.id}_helptext`
    );

    if (livre) {
      novo.type = "text";
      novo.maxLength = Number(
        marca.dataset.modeloMaxlength || 120
      );
      novo.placeholder = "Informe o modelo";
      novo.value = anterior;
    }

    modelo.replaceWith(novo);
    modelo = novo;

    if (!livre) {
      modelo.replaceChildren(
        new Option(
          marca.value
            ? "Selecione o modelo"
            : "Selecione primeiro a marca",
          ""
        )
      );

      for (const nome of nomes) {
        modelo.add(
          new Option(
            nome,
            nome,
            false,
            nome === anterior
          )
        );
      }
    }
  }

  criarBotao(marca, "marca");
  criarBotao(modelo, "modelo");

  marca.addEventListener("change", () => {
    atualizar(false);
  });

  atualizar(true);
});