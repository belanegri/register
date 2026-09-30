(() => {
const precos = JSON.parse(document.getElementById('precos-catalogo').textContent);
const itens = document.getElementById('itens');
document.getElementById('adicionar-item').addEventListener('click', () => {
 const count = document.getElementById('id_itens-TOTAL_FORMS');
 if (+count.value >= 100) return;
 itens.insertAdjacentHTML('beforeend', document.getElementById('novo-item').innerHTML.replaceAll('__prefix__', count.value));
 count.value = +count.value + 1;
});
itens.addEventListener('change', e => {
 const tipo = e.target.name.endsWith('-peca') ? 'peca' : e.target.name.endsWith('-servico') ? 'servico' : null;
 if (!tipo || !e.target.value) return;
 const row = e.target.closest('.item-documento');
 row.querySelector('[name$="-' + (tipo === 'peca' ? 'servico' : 'peca') + '"]').value = '';
 row.querySelector('[name$="-preco"]').value = precos[tipo][e.target.value];
});
})();