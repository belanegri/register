(() => {
  const campo = document.getElementById('id_plano_personalizado');
  if (!campo || campo.disabled) return;
  const form = campo.form;
  const el = nome => form.querySelector('#id_' + nome);
  const moeda = valor => Math.round(Number(String(valor || '0').replace(',', '.')) * 100);
  const formatar = centavos => (centavos / 100).toFixed(2);
  const formas = el('forma_prevista');
  const painel = document.createElement('div');
  painel.className = 'mt-2';
  campo.hidden = true;
  campo.after(painel);
  const acoes = document.createElement('div');
  acoes.className = 'd-flex flex-wrap gap-2 mb-3';
  painel.append(acoes);
  const lista = document.createElement('div');
  lista.className = 'd-grid gap-2';
  painel.append(lista);
  const resumo = document.createElement('p');
  resumo.className = 'mt-2 text-muted';
  resumo.setAttribute('aria-live', 'polite');
  painel.append(resumo);
  function botao(texto, acao) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'btn btn-sm btn-outline-primary'; b.textContent = texto;
    b.addEventListener('click', acao); acoes.append(b);
  }
  function sincronizar() {
    const linhas = [...lista.children];
    campo.value = linhas.map(l => [...l.querySelectorAll('input,select')].map(c => c.value).join(';')).join('\n');
    const soma = linhas.reduce((s,l) => s + moeda(l.querySelector('[data-valor]').value), 0);
    resumo.textContent = linhas.length ? linhas.length + ' lançamentos · Soma: R$ ' + formatar(soma).replace('.', ',') + '. Confira o total antes de salvar.' : 'Use parcelas automáticas ou monte um plano com valores, datas e formas diferentes.';
    // A entrada já faz parte do plano personalizado.
    if (linhas.length) { if (el('entrada')) el('entrada').value = ''; if (el('data_entrada')) el('data_entrada').value = ''; }
    campo.dispatchEvent(new Event('input', {bubbles:true}));
  }
  function linha(data='', valor='', forma='') {
    if (lista.children.length >= 120) return;
    const row = document.createElement('div'); row.className = 'row g-2 align-items-end';
    function coluna(rotulo, controle, classe) {
      const div = document.createElement('div'); div.className = classe;
      const label = document.createElement('label'); label.textContent = rotulo;
      controle.setAttribute('aria-label', rotulo); controle.classList.add('form-control');
      div.append(label, controle); row.append(div);
    }
    const date = document.createElement('input'); date.type='date'; date.value=data;
    const amount = document.createElement('input'); amount.type='number'; amount.step='.01'; amount.min='.01'; amount.value=valor.replace(',', '.'); amount.dataset.valor='1';
    const select = document.createElement('select');
    if (formas) [...formas.options].forEach(o => select.add(new Option(o.text, o.value)));
    select.value = forma || formas?.value || '';
    coluna('Vencimento', date, 'col-6 col-md-3'); coluna('Valor', amount, 'col-6 col-md-3'); coluna('Forma prevista', select, 'col-10 col-md-5');
    const excluir = document.createElement('button'); excluir.type='button'; excluir.className='btn btn-outline-danger col-2 col-md-1'; excluir.textContent='×'; excluir.setAttribute('aria-label','Remover parcela');
    excluir.addEventListener('click', () => {row.remove(); sincronizar();}); row.append(excluir);
    row.addEventListener('input', sincronizar); row.addEventListener('change', sincronizar); lista.append(row);
  }
  botao('Adicionar parcela', () => {linha(el('vencimento')?.value || ''); sincronizar();});
  botao('Montar parcelas para ajustar', () => {
    const total = moeda(el('valor_original')?.value || form.dataset.total);
    const ajustes = ['juros','multa','acrescimos'].reduce((s,k) => s+moeda(el(k)?.value), 0) - moeda(el('desconto')?.value);
    const entrada = moeda(el('entrada')?.value);
    const count = Number(el('quantidade_lancamentos')?.value || 1);
    const inicio = el('vencimento')?.value;
    if (!inicio || !Number.isInteger(count) || count < 1 || count + Boolean(entrada) > 120 || total + ajustes <= entrada) { resumo.textContent='Informe total, primeiro vencimento e quantidade válidos.'; return; }
    lista.replaceChildren();
    if (entrada) linha(el('data_entrada')?.value || inicio, formatar(entrada));
    const saldo = total + ajustes - entrada, base = Math.floor(saldo/count), resto = saldo % count;
    const freq = el('frequencia')?.value || 'mensal';
    const [ano,mes,dia] = inicio.split('-').map(Number);
    for(let i=0;i<count;i++) {
      let data;
      if (['semanal','quinzenal','dias'].includes(freq)) data = new Date(Date.UTC(ano,mes-1,dia+i*(freq==='semanal'?7:freq==='quinzenal'?15:Number(el('intervalo_dias')?.value || 30))));
      else {const passo = {mensal:1,bimestral:2,trimestral:3,semestral:6,anual:12}[freq] || 1; data = new Date(Date.UTC(ano,mes-1+i*passo,1)); const ultimo = new Date(Date.UTC(data.getUTCFullYear(),data.getUTCMonth()+1,0)).getUTCDate(); data.setUTCDate(Math.min(dia,ultimo));}
      linha(data.toISOString().slice(0,10), formatar(base+(i<resto?1:0)));
    }
    if (el('modo')) el('modo').value='parcelada';
    sincronizar();
  });
  botao('Usar cálculo automático', () => {lista.replaceChildren(); sincronizar();});
  campo.value.split('\n').filter(Boolean).forEach(l => linha(...l.split(';')));
  sincronizar();
})();
