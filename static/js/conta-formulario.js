(() => {
  const form = document.getElementById('conta-form');
  if (!form) return;

  const el = name => document.getElementById('id_' + name);

  const output = (id, value) => {
    const elemento = document.getElementById(id);
    if (elemento) elemento.textContent = value;
  };

  const currency = new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  });

  const money = cents =>
    Number.isFinite(cents)
      ? currency.format(cents / 100)
      : 'Confira os valores';

  const cents = value => {
    let text = String(value || '0').trim();

    if (text.includes(',')) {
      text = text
        .replaceAll('.', '')
        .replace(',', '.');
    }

    return /^\d+(\.\d{1,2})?$/.test(text)
      ? Math.round(Number(text) * 100)
      : NaN;
  };

  const dividir = (value, count, index) =>
    Math.floor(value / count) +
    (index < value % count ? 1 : 0);

  function dataParcela(value, index, frequency) {
    const [year, month, day] = value
      .split('-')
      .map(Number);

    if (!year || !month || !day) return '';

    let date;

    if (frequency === 'semanal') {
      date = new Date(
        Date.UTC(
          year,
          month - 1,
          day + index * 7
        )
      );
    } else {
      const step = {
        mensal: 1,
        bimestral: 2,
        trimestral: 3,
        semestral: 6,
        anual: 12
      }[frequency] || 1;

      const base = new Date(
        Date.UTC(
          year,
          month - 1 + index * step,
          1
        )
      );

      const last = new Date(
        Date.UTC(
          base.getUTCFullYear(),
          base.getUTCMonth() + 1,
          0
        )
      ).getUTCDate();

      date = new Date(
        Date.UTC(
          base.getUTCFullYear(),
          base.getUTCMonth(),
          Math.min(day, last)
        )
      );
    }

    return new Intl.DateTimeFormat(
      'pt-BR',
      { timeZone: 'UTC' }
    ).format(date);
  }

  function atualizar() {
    const camposValores = [
      'valor_original',
      'desconto',
      'juros',
      'multa',
      'acrescimos'
    ];

    const values = camposValores.map(name => {
      const campo = el(name);
      return campo ? cents(campo.value) : 0;
    });

    const [
      original,
      discount,
      interest,
      penalty,
      extras
    ] = values;

    const total =
      original -
      discount +
      interest +
      penalty +
      extras;

    const editing =
      form.dataset.editando === '1';

    const modoCampo = el('modo');
    const quantidadeCampo =
      el('quantidade_lancamentos');
    const frequenciaCampo =
      el('frequencia');

    const mode =
      modoCampo ? modoCampo.value : 'unica';

    const count =
      quantidadeCampo
        ? Number(quantidadeCampo.value)
        : 0;

    const series =
      mode !== 'unica' && !editing;

    const campoFrequencia = form.querySelector(
      '[data-campo="frequencia"]'
    );

    const campoQuantidade = form.querySelector(
      '[data-campo="quantidade_lancamentos"]'
    );

    if (campoFrequencia) {
      campoFrequencia.hidden =
        mode !== 'recorrente';
    }

    if (campoQuantidade) {
      campoQuantidade.hidden =
        mode === 'unica';
    }

    if (quantidadeCampo) {
      quantidadeCampo.required = series;
    }

    if (frequenciaCampo) {
      frequenciaCampo.required =
        mode === 'recorrente' && !editing;
    }

    const formaCampo = el('forma_prevista');

    const forma =
      formaCampo?.selectedOptions[0]
        ?.textContent || '';

    const pixCampo = el('pix_copia_cola');

    const containerPix = form.querySelector(
      '[data-campo="pix_copia_cola"]'
    );

    if (containerPix && pixCampo) {
      containerPix.hidden =
        !/pix/i.test(forma) &&
        !pixCampo.value;
    }

    output(
      'conta-total',
      money(total)
    );

    output(
      'resumo-original',
      money(original)
    );

    output(
      'resumo-desconto',
      money(discount)
    );

    output(
      'resumo-acrescimos',
      money(
        interest +
        penalty +
        extras
      )
    );

    if (editing) {
      output(
        'resumo-saldo',
        money(
          total -
          cents(form.dataset.pago)
        )
      );
    }

    output(
      'resumo-titulo',
      mode === 'recorrente' &&
      !editing
        ? 'Valor de cada lançamento'
        : 'Valor total'
    );

    output(
      'resumo-legenda',
      'Original − desconto + juros + multa + acréscimos.'
    );

    const info =
      document.getElementById('serie-info');

    if (info) {
      info.hidden = !series;

      info.textContent =
        mode === 'parcelada'
          ? 'O valor informado será dividido em parcelas mensais. A data de vencimento acima será a da primeira parcela.'
          : 'O mesmo valor será repetido na frequência escolhida. Serão gerados somente os lançamentos informados, sem renovação automática.';
    }

    const preview =
      document.getElementById('serie-previa');

    const vencimentoCampo =
      el('vencimento');

    if (preview) {
      preview.hidden =
        !series ||
        count < 2 ||
        count > 120 ||
        !Number.isInteger(count) ||
        !Number.isFinite(total) ||
        total <= 0 ||
        !vencimentoCampo?.value ||
        (
          mode === 'recorrente' &&
          !frequenciaCampo?.value
        );
    }

    const tbody =
      document.getElementById('serie-linhas');

    if (tbody) {
      tbody.replaceChildren();
    }

    if (
      preview &&
      !preview.hidden &&
      tbody
    ) {
      for (
        let i = 0;
        i < Math.min(count, 12);
        i++
      ) {
        const amount =
          mode === 'parcelada'
            ? values.reduce(
                (sum, value, j) =>
                  sum +
                  (j === 1 ? -1 : 1) *
                    dividir(
                      value,
                      count,
                      i
                    ),
                0
              )
            : total;

        const row =
          document.createElement('tr');

        [
          String(i + 1) +
            ' de ' +
            count,

          dataParcela(
            vencimentoCampo.value,
            i,
            mode === 'parcelada'
              ? 'mensal'
              : frequenciaCampo.value
          ),

          money(amount)
        ].forEach((text, index) => {
          const cell =
            document.createElement('td');

          cell.textContent = text;

          if (index === 2) {
            cell.className =
              'text-end';
          }

          row.append(cell);
        });

        tbody.append(row);
      }

      output(
        'serie-limite',
        (
          count > 12
            ? 'Mostrando os 12 primeiros. '
            : ''
        ) +
        count +
        ' lançamentos · soma ' +
        money(
          mode === 'recorrente'
            ? total * count
            : total
        )
      );
    }
  }


  // ==================================================
  // LEITOR DE BOLETO
  // ==================================================

  const codigoBoleto = el('codigo_boleto');
  const botaoBoleto = document.getElementById('processar-boleto');
  const statusBoleto = document.getElementById('boleto-status');
  let leitura = 0;
  let timerBoleto;
  async function processarBoleto() {
    const numero = ++leitura;
    const codigo = codigoBoleto.value;
    statusBoleto.textContent = 'Validando boleto…';
    try {
      const resposta = await fetch(form.dataset.boletoUrl, {
        method: 'POST', credentials: 'same-origin',
        headers: {'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value},
        body: new URLSearchParams({codigo_boleto: codigo, ciclo_boleto: el('ciclo_boleto').value || 'atual'})
      });
      const dados = await resposta.json();
      if (numero !== leitura || codigo !== codigoBoleto.value) return;
      if (!resposta.ok) throw new Error(dados.erro || 'Não foi possível validar o boleto.');
      if (dados.valor !== null && !el('valor_original').disabled) el('valor_original').value = dados.valor;
      if (dados.vencimento !== null) el('vencimento').value = dados.vencimento;
      statusBoleto.textContent = 'Código válido. Confira valor e vencimento no documento.';
      atualizar();
    } catch (erro) {
      if (numero === leitura) statusBoleto.textContent = erro.message || 'Falha na leitura. Tente novamente.';
    }
  }
  if (codigoBoleto && botaoBoleto) {
    botaoBoleto.addEventListener('click', () => { clearTimeout(timerBoleto); processarBoleto(); });
    codigoBoleto.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault(); clearTimeout(timerBoleto); processarBoleto();
      }
    });
    codigoBoleto.addEventListener('input', () => {
      ++leitura; clearTimeout(timerBoleto); statusBoleto.textContent = '';
      if ([44, 47].includes(codigoBoleto.value.replace(/[.\s-]/g, '').length)) timerBoleto = setTimeout(processarBoleto, 350);
    });
    el('ciclo_boleto').addEventListener('change', () => { if (codigoBoleto.value.trim()) processarBoleto(); });
  }

  form.addEventListener(
    'input',
    atualizar
  );

  form.addEventListener(
    'change',
    atualizar
  );

  atualizar();
})();