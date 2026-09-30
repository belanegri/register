(() => {
  const form = document.getElementById('conta-form');
  if (!form) return;
  const el = name => document.getElementById('id_' + name);
  const output = (id, value) => { document.getElementById(id).textContent = value; };
  const currency = new Intl.NumberFormat('pt-BR', {style: 'currency', currency: 'BRL'});
  const money = cents => Number.isFinite(cents) ? currency.format(cents / 100) : 'Confira os valores';
  const cents = value => {
    let text = String(value || '0').trim();
    if (text.includes(',')) text = text.replaceAll('.', '').replace(',', '.');
    return /^\d+(\.\d{1,2})?$/.test(text) ? Math.round(Number(text) * 100) : NaN;
  };
  const dividir = (value, count, index) => Math.floor(value / count) + (index < value % count ? 1 : 0);
  function dataParcela(value, index, frequency) {
    const [year, month, day] = value.split('-').map(Number);
    if (!year || !month || !day) return '';
    let date;
    if (frequency === 'semanal') date = new Date(Date.UTC(year, month - 1, day + index * 7));
    else {
      const step = {mensal:1, bimestral:2, trimestral:3, semestral:6, anual:12}[frequency] || 1;
      const base = new Date(Date.UTC(year, month - 1 + index * step, 1));
      const last = new Date(Date.UTC(base.getUTCFullYear(), base.getUTCMonth() + 1, 0)).getUTCDate();
      date = new Date(Date.UTC(base.getUTCFullYear(), base.getUTCMonth(), Math.min(day, last)));
    }
    return new Intl.DateTimeFormat('pt-BR', {timeZone:'UTC'}).format(date);
  }
  function atualizar() {
    const values = ['valor_original', 'desconto', 'juros', 'multa', 'acrescimos'].map(name => cents(el(name).value));
    const [original, discount, interest, penalty, extras] = values;
    const total = original - discount + interest + penalty + extras;
    const editing = form.dataset.editando === '1';
    const mode = el('modo').value;
    const count = Number(el('quantidade_lancamentos').value);
    const series = mode !== 'unica' && !editing;
    form.querySelector('[data-campo="frequencia"]').hidden = mode !== 'recorrente';
    form.querySelector('[data-campo="quantidade_lancamentos"]').hidden = mode === 'unica';
    el('quantidade_lancamentos').required = series;
    el('frequencia').required = mode === 'recorrente' && !editing;
    const forma = el('forma_prevista').selectedOptions[0]?.textContent || '';
    form.querySelector('[data-campo="pix_copia_cola"]').hidden = !/pix/i.test(forma) && !el('pix_copia_cola').value;
    output('conta-total', money(total));
    output('resumo-original', money(original));
    output('resumo-desconto', money(discount));
    output('resumo-acrescimos', money(interest + penalty + extras));
    if (editing) output('resumo-saldo', money(total - cents(form.dataset.pago)));
    output('resumo-titulo', mode === 'recorrente' && !editing ? 'Valor de cada lançamento' : 'Valor total');
    output('resumo-legenda', 'Original − desconto + juros + multa + acréscimos.');
    const info = document.getElementById('serie-info');
    info.hidden = !series;
    info.textContent = mode === 'parcelada'
      ? 'O valor informado será dividido em parcelas mensais. A data de vencimento acima será a da primeira parcela.'
      : 'O mesmo valor será repetido na frequência escolhida. Serão gerados somente os lançamentos informados, sem renovação automática.';
    const preview = document.getElementById('serie-previa');
    preview.hidden = !series || count < 2 || count > 120 || !Number.isInteger(count) || !Number.isFinite(total) || total <= 0 || !el('vencimento').value || (mode === 'recorrente' && !el('frequencia').value);
    const tbody = document.getElementById('serie-linhas');
    tbody.replaceChildren();
    if (!preview.hidden) {
      for (let i=0; i<Math.min(count, 12); i++) {
        const amount = mode === 'parcelada' ? values.reduce((sum, value, j) => sum + (j === 1 ? -1 : 1) * dividir(value, count, i), 0) : total;
        const row = document.createElement('tr');
        [String(i + 1) + ' de ' + count, dataParcela(el('vencimento').value, i, mode === 'parcelada' ? 'mensal' : el('frequencia').value), money(amount)].forEach((text, index) => {
          const cell = document.createElement('td'); cell.textContent = text;
          if (index === 2) cell.className = 'text-end';
          row.append(cell);
        });
        tbody.append(row);
      }
      output('serie-limite', (count > 12 ? 'Mostrando os 12 primeiros. ' : '') + count + ' lançamentos · soma ' + money(mode === 'recorrente' ? total * count : total));
    }
  }
  form.addEventListener('input', atualizar);
  form.addEventListener('change', atualizar);
  atualizar();
})();
