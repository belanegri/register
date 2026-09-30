(() => {
  const precos = JSON.parse(document.getElementById('precos-catalogo').textContent);
  const itens = document.getElementById('itens');
  const moeda = new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'});
  const cents = value => {
    let s = String(value || '0').trim();
    if (s.includes(',')) s=s.replaceAll('.','').replace(',','.');
    return /^\d+(\.\d{0,2})?$/.test(s) ? Math.round(Number(s)*100) : NaN;
  };
  function atualizar() {
    let pecas=0, servicos=0;
    itens.querySelectorAll('.item-documento').forEach(row => {
      const apagado=row.querySelector('[name$="-DELETE"]').checked;
      row.classList.toggle('is-removed',apagado);
      const p=row.querySelector('[name$="-peca"]').value;
      const s=row.querySelector('[name$="-servico"]').value;
      const qtd=Number(row.querySelector('[name$="-quantidade"]').value);
      const total=apagado || (!p && !s) ? 0 : qtd*cents(row.querySelector('[name$="-preco"]').value);
      row.querySelector('.item-total').textContent=Number.isFinite(total) ? moeda.format(total/100) : 'Confira o valor';
      if(p) pecas+=total; else if(s) servicos+=total;
    });
    document.getElementById('subtotal-pecas').textContent=moeda.format(pecas/100);
    document.getElementById('subtotal-servicos').textContent=moeda.format(servicos/100);
    const total=pecas+servicos-cents(document.getElementById('id_desconto').value);
    document.getElementById('total-documento').textContent=Number.isFinite(total) && total>=0 ? moeda.format(total/100) : 'Confira os valores';
  }
  document.getElementById('adicionar-item').addEventListener('click', () => {
    const count = document.getElementById('id_itens-TOTAL_FORMS');
    if (+count.value >= 100) return;
    itens.insertAdjacentHTML('beforeend', document.getElementById('novo-item').innerHTML.replaceAll('__prefix__',count.value));
    count.value=+count.value+1;
    itens.lastElementChild.querySelector('select').focus();
    atualizar();
  });
  itens.addEventListener('change', e => {
    const tipo=e.target.name.endsWith('-peca') ? 'peca' : e.target.name.endsWith('-servico') ? 'servico' : null;
    if(tipo && e.target.value) {
      const row=e.target.closest('.item-documento');
      row.querySelector('[name$="-'+(tipo==='peca' ? 'servico' : 'peca')+'"]').value='';
      row.querySelector('[name$="-preco"]').value=precos[tipo][e.target.value];
    }
    atualizar();
  });
  itens.addEventListener('input',atualizar);
  document.getElementById('id_desconto').addEventListener('input',atualizar);
  atualizar();
})();

(() => {
  const condicao = document.getElementById('id_condicao_pagamento');
  const parcelamento = document.getElementById('parcelamento-campos');
  const parcelas = document.getElementById('id_parcelas');
  const vencimento = document.getElementById('id_primeiro_vencimento');

  if (!condicao || !parcelamento) return;

  function atualizarParcelamento() {
    const parcelado = condicao.value === 'parcelado';

    parcelamento.style.display = parcelado ? 'grid' : 'none';

    if (!parcelado) {
      if (parcelas) parcelas.value = '1';
      if (vencimento) vencimento.value = '';
    } else if (parcelas && Number(parcelas.value) < 2) {
      parcelas.value = '2';
    }
  }

  condicao.addEventListener('change', atualizarParcelamento);
  atualizarParcelamento();
})();