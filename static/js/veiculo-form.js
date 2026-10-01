document.addEventListener("DOMContentLoaded", () => {
  const marca = document.getElementById("id_marca");
  let modelo = document.getElementById(
    marca?.dataset.modeloCampo || "id_aplicacao"
  );

  const novaMarca = document.getElementById(
    marca?.dataset.novaMarcaCampo || "id_nova_marca"
  );

  const novoModelo = document.getElementById(
    marca?.dataset.novoModeloCampo || "id_novo_modelo"
  );

  if (!marca || !modelo || !marca.dataset.modelos) return;

  const catalogo = JSON.parse(marca.dataset.modelos);
  const valorNovaMarca = marca.dataset.novaMarca || "__nova_marca__";
  const valorNovoModelo = marca.dataset.novoModelo || "__novo_modelo__";

  function grupoDoCampo(campo) {
    if (!campo) return null;

    return (
      campo.closest(".mb-3") ||
      campo.closest(".form-group") ||
      campo.parentElement
    );
  }

  const grupoNovaMarca = grupoDoCampo(novaMarca);
  const grupoNovoModelo = grupoDoCampo(novoModelo);

  function mostrar(campo, grupo, exibir) {
    if (!campo) return;

    if (grupo) {
      grupo.style.display = exibir ? "" : "none";
    }

    campo.hidden = !exibir;

    if (!exibir) {
      campo.value = "";
    }
  }

  function atualizarModelo(preservar = false) {
    const anterior = preservar ? modelo.value : "";
    const marcaSelecionada = marca.value;

    mostrar(
      novaMarca,
      grupoNovaMarca,
      marcaSelecionada === valorNovaMarca
    );

    if (!marcaSelecionada) {
      mostrar(novoModelo, grupoNovoModelo, false);

      if (modelo.tagName.toLowerCase() !== "select") {
        const novoSelect = document.createElement("select");
        novoSelect.id = modelo.id;
        novoSelect.name = modelo.name;
        novoSelect.className = modelo.className;
        modelo.replaceWith(novoSelect);
        modelo = novoSelect;
      }

      modelo.replaceChildren(
        new Option("Selecione primeiro a marca", "")
      );

      return;
    }

    if (marcaSelecionada === valorNovaMarca) {
      mostrar(novoModelo, grupoNovoModelo, true);

      if (modelo.tagName.toLowerCase() !== "select") {
        const novoSelect = document.createElement("select");
        novoSelect.id = modelo.id;
        novoSelect.name = modelo.name;
        novoSelect.className = modelo.className;
        modelo.replaceWith(novoSelect);
        modelo = novoSelect;
      }

      modelo.replaceChildren(
        new Option("+ Novo modelo", valorNovoModelo, true, true)
      );

      return;
    }

    const modelos = catalogo[marcaSelecionada] || [];

    if (modelo.tagName.toLowerCase() !== "select") {
      const novoSelect = document.createElement("select");
      novoSelect.id = modelo.id;
      novoSelect.name = modelo.name;
      novoSelect.className = modelo.className;
      modelo.replaceWith(novoSelect);
      modelo = novoSelect;
    }

    modelo.replaceChildren(
      new Option("Selecione o modelo", "")
    );

    for (const nome of modelos) {
      modelo.add(
        new Option(nome, nome, false, nome === anterior)
      );
    }

    modelo.add(
      new Option(
        "+ Novo modelo",
        valorNovoModelo,
        false,
        anterior === valorNovoModelo
      )
    );

    mostrar(
      novoModelo,
      grupoNovoModelo,
      modelo.value === valorNovoModelo
    );
  }

  marca.addEventListener("change", () => {
    atualizarModelo(false);
  });

  document.addEventListener("change", (event) => {
    if (event.target === modelo) {
      mostrar(
        novoModelo,
        grupoNovoModelo,
        modelo.value === valorNovoModelo
      );
    }
  });

  atualizarModelo(true);
});