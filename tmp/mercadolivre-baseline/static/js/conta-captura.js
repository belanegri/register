/* Dados extraídos são sugestões. Nenhuma captura envia o cadastro ou paga a conta. */
(() => {
  'use strict';
  const form = document.getElementById('conta-form');
  if (!form) return;
  const get = id => document.getElementById(id);
  const assets = new URL(form.dataset.capturaAssets, location.origin).href;
  const status = get('captura-status');
  const resultado = get('captura-resultado');
  const labels = {fornecedor:'Fornecedor / Favorecido', descricao:'Descrição', numero_documento:'Número do documento',
    valor_original:'Valor original', vencimento:'Vencimento', emissao:'Emissão', codigo_boleto:'Código do boleto',
    pix_copia_cola:'PIX Copia e Cola', forma_prevista:'Forma de pagamento'};
  let serial = 0, timer, worker, pdfTask, controller, opcoes = [], avisos = [], arquivoLido = null;
  let checks = [], sourceAtivo = null, timeoutJob;
  const scripts = new Map();
  function mensagem(texto, erro = false) {status.textContent = texto; status.classList.toggle('erro', erro);}
  function carregar(src) {
    if (!scripts.has(src)) scripts.set(src, new Promise((resolve, reject) => {
      const script = document.createElement('script'); script.src = src;
      script.onload = resolve; script.onerror = () => {scripts.delete(src); reject(new Error('Não foi possível carregar a leitura. Confira a conexão.'));};
      document.head.append(script);
    }));
    return scripts.get(src);
  }
  function encerrar() {
    ++serial; clearTimeout(timer); clearTimeout(timeoutJob); controller?.abort(); controller = null;
    worker?.terminate(); worker = null;
    pdfTask?.destroy(); pdfTask = null;
    get('captura-cancelar').hidden = true;
  }
  function iniciar() {
    encerrar(); resultado.hidden = true; arquivoLido = null; sourceAtivo = null;
    get('captura-cancelar').hidden = false;
    const job = serial;
    timeoutJob = setTimeout(() => {if (job === serial) {encerrar(); mensagem('A leitura demorou demais. Tente uma página ou imagem menor.', true);}}, 90000);
    return job;
  }
  function ativo(job) {if (job !== serial) throw new Error('Leitura cancelada.');}
  async function consultar(dados, job) {
    controller = new AbortController();
    const response = await fetch(form.dataset.capturaUrl, {method:'POST', credentials:'same-origin', signal:controller.signal,
      headers:{'Content-Type':'application/json', 'X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value}, body:JSON.stringify(dados)});
    ativo(job);
    if (response.redirected) throw new Error('Sua sessão expirou. Entre novamente antes de ler a cobrança.');
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Não foi possível validar a leitura. Atualize a página e tente novamente.');
    const data = await response.json(); ativo(job);
    if (!response.ok) throw new Error(data.erro || 'Não foi possível ler esta cobrança.');
    return data;
  }
  function renderizar() {
    const opcao = opcoes[Number(get('captura-opcao').value)];
    const campos = get('captura-campos'); campos.replaceChildren(); checks = [];
    const lista = get('captura-avisos'); lista.replaceChildren();
    for (const aviso of [...avisos, ...(opcao?.avisos || [])]) {const li = document.createElement('li'); li.textContent = aviso; lista.append(li);}
    const infos = get('captura-informacoes'); infos.replaceChildren();
    for (const [label, valor] of Object.entries(opcao?.informacoes || {})) {
      const dt = document.createElement('dt'); dt.textContent = label;
      const dd = document.createElement('dd'); dd.textContent = valor; infos.append(dt, dd);
    }
    for (const [nome, dado] of Object.entries(opcao?.campos || {})) {
      if (!(nome in labels)) continue;
      const destino = get('id_' + nome); if (!destino) continue;
      const label = document.createElement('label'); label.className = 'captura-check captura-linha';
      const check = document.createElement('input'); check.type = 'checkbox'; check.dataset.campo = nome;
      check.disabled = destino.disabled; check.checked = !destino.disabled && !destino.value.trim();
      const texto = document.createElement('span');
      const titulo = document.createElement('strong'); titulo.textContent = labels[nome] + ': ';
      const valor = document.createElement('span'); valor.textContent = dado.texto || dado.valor;
      const origem = document.createElement('small'); origem.textContent = dado.origem;
      if (destino.disabled) origem.textContent += ' · Campo protegido por pagamentos já registrados';
      else if (destino.value) origem.textContent += ' · Já preenchido: ' + (nome === 'forma_prevista' ? destino.selectedOptions[0]?.textContent : destino.value);
      texto.append(titulo, valor, origem); label.append(check, texto); campos.append(label);
      checks.push({check, destino, dado, nome});
    }
    get('captura-observacoes').checked = false;
    get('captura-anexar-label').hidden = !arquivoLido;
    get('captura-aplicar').disabled = !opcao;
  }
  function mostrar(data, job, file = null) {
    ativo(job); clearTimeout(timeoutJob); get('captura-cancelar').hidden = true;
    opcoes = data.opcoes; avisos = data.avisos || []; arquivoLido = file;
    const seletor = get('captura-opcao'); seletor.replaceChildren();
    opcoes.forEach((o, i) => {const opt = document.createElement('option'); opt.value = i; opt.textContent = `${i+1}. ${o.titulo}`; seletor.append(opt);});
    resultado.hidden = false; renderizar();
    mensagem(opcoes.length ? 'Leitura concluída. Confira as sugestões abaixo e aplique os campos desejados.' : 'Nenhuma informação identificada com segurança. Confira os avisos abaixo.', !opcoes.length);
  }
  async function lerCodigo(input, tipo = 'auto') {
    if (!input?.value.trim()) {mensagem('Cole um código completo para iniciar.', true); return;}
    const job = iniciar(), valor = input.value;
    sourceAtivo = {input, valor};
    mensagem('Validando e identificando as informações da cobrança…');
    try {
      const data = await consultar({tipo, codigo:valor, ciclo:get('id_ciclo_boleto').value || 'atual'}, job);
      if (input.value !== valor) return;
      mostrar(data, job);
    } catch (e) {if (job === serial) {mensagem(e.message, true); get('captura-cancelar').hidden = true; clearTimeout(timeoutJob);}}
  }
  async function canvasImagem(file) {
    const bitmap = await createImageBitmap(file);
    try {
      if (bitmap.width * bitmap.height > 40000000) throw new Error('Imagem muito grande. Use uma foto de até 40 megapixels.');
      const escala = Math.min(1, 2200 / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement('canvas'); canvas.width = Math.round(bitmap.width * escala); canvas.height = Math.round(bitmap.height * escala);
      const ctx = canvas.getContext('2d'); ctx.fillStyle = 'white'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      return canvas;
    } finally {bitmap.close();}
  }
  async function reconhecer(canvas, job, textoNecessario) {
    await carregar(assets + 'zxing-reader.js'); ativo(job);
    ZXingWASM.prepareZXingModule({overrides:{locateFile:() => assets + 'zxing_reader.wasm'}});
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    const codigos = (await ZXingWASM.readBarcodes(pixels, {formats:['QRCode','ITF','Code128'], tryHarder:true, maxNumberOfSymbols:10})).map(c => c.text);
    ativo(job);
    let texto = '';
    if (textoNecessario) {
      mensagem('Reconhecendo o texto da imagem. Mantenha esta página aberta…');
      await carregar(assets + 'tesseract.min.js'); ativo(job);
      if (!worker) {
        const novo = await Tesseract.createWorker('por', 1, {workerPath:assets+'worker.min.js', corePath:assets+'core', langPath:assets+'lang',
          workerBlobURL:false, cacheMethod:'none', logger:m => {if (job === serial && m.status === 'recognizing text') mensagem('Lendo texto: '+Math.round(m.progress*100)+'%');}});
        if (job !== serial) {await novo.terminate(); ativo(job);}
        worker = novo;
      }
      const r = await worker.recognize(canvas); ativo(job); texto = r.data.text;
    }
    return {texto, codigos};
  }
  async function lerArquivo() {
    const file = get('captura-arquivo').files[0];
    if (!file) {mensagem('Selecione um PDF, JPG ou PNG.', true); return;}
    if (file.size > 10 * 1024 * 1024 || !/\.(pdf|png|jpe?g)$/i.test(file.name)) {mensagem('Use PDF, JPG ou PNG com até 10 MB.', true); return;}
    const job = iniciar(); mensagem('Preparando a leitura do documento…');
    let texto = '', codigos = [];
    try {
      if (/\.pdf$/i.test(file.name)) {
        const pdfjs = await import(assets+'pdf.mjs'); ativo(job);
        pdfjs.GlobalWorkerOptions.workerSrc = assets+'pdf.worker.mjs';
        pdfTask = pdfjs.getDocument({data:new Uint8Array(await file.arrayBuffer()), isEvalSupported:false,
          cMapUrl:assets+'cmaps/', cMapPacked:true, standardFontDataUrl:assets+'standard_fonts/', wasmUrl:assets+'pdf-wasm/'});
        const doc = await pdfTask.promise; ativo(job);
        if (doc.numPages > 3) throw new Error('Selecione um documento de até 3 páginas, com uma cobrança por vez.');
        for (let i = 1; i <= doc.numPages; i++) {
          ativo(job); mensagem(`Lendo página ${i} de ${doc.numPages}…`);
          const page = await doc.getPage(i), content = await page.getTextContent(); ativo(job);
          let trecho = '', y = null;
          for (const item of content.items) {
            if (!('str' in item)) continue;
            if (y !== null && Math.abs(item.transform[5] - y) > 3) trecho += '\n';
            trecho += item.str + ' '; if (item.hasEOL) trecho += '\n'; y = item.transform[5];
          }
          const view = page.getViewport({scale:1}), scale = Math.min(2.5, 2200 / Math.max(view.width, view.height));
          const viewport = page.getViewport({scale}), canvas = document.createElement('canvas');
          canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
          await page.render({canvasContext:canvas.getContext('2d'), viewport}).promise; ativo(job);
          const leitura = await reconhecer(canvas, job, trecho.replace(/\s/g, '').length < 40);
          texto += (leitura.texto || trecho) + '\n'; codigos.push(...leitura.codigos);
          canvas.width = canvas.height = 0; page.cleanup();
        }
      } else {
        const canvas = await canvasImagem(file); ativo(job);
        const leitura = await reconhecer(canvas, job, true); texto = leitura.texto; codigos = leitura.codigos;
        canvas.width = canvas.height = 0;
      }
      ativo(job); mensagem('Validando os dados encontrados…');
      const data = await consultar({tipo:'documento', texto, codigos:[...new Set(codigos)].slice(0,20), ciclo:get('id_ciclo_boleto').value || 'atual'}, job);
      mostrar(data, job, file);
    } catch (e) {
      if (job === serial) {mensagem(e.name === 'PasswordException' ? 'PDF protegido por senha. Envie uma cópia sem senha ou uma foto.' : 'Não foi possível concluir a leitura. '+e.message, true); clearTimeout(timeoutJob); get('captura-cancelar').hidden = true;}
    } finally {
      if (job === serial) {await worker?.terminate(); worker = null; await pdfTask?.destroy(); pdfTask = null;}
    }
  }
  get('captura-aplicar').addEventListener('click', () => {
    if (sourceAtivo && sourceAtivo.input.value !== sourceAtivo.valor) {resultado.hidden = true; mensagem('O código mudou. Faça uma nova leitura.', true); return;}
    const anexos = get('id_documentos');
    if (arquivoLido && get('captura-anexar').checked) {
      const arquivos = [...anexos.files];
      if (!arquivos.some(f => f.name === arquivoLido.name && f.size === arquivoLido.size && f.lastModified === arquivoLido.lastModified)) {
        if (arquivos.length >= 10) {mensagem('Já existem 10 anexos. Remova um ou desmarque a opção de anexar.', true); return;}
        const dt = new DataTransfer(); [...arquivos, arquivoLido].forEach(f => dt.items.add(f)); anexos.files = dt.files;
      }
    }
    let count = 0;
    for (const {check, destino, dado, nome} of checks) {
      if (check.checked && !destino.disabled) {
        destino.value = nome === 'valor_original' ? dado.valor.replace('.', ',') : dado.valor; count++;
      }
    }
    const opcao = opcoes[Number(get('captura-opcao').value)];
    if (get('captura-observacoes').checked && opcao) {
      const bloco = 'Dados capturados — conferir:\n'+Object.entries(opcao.informacoes).map(([k,v]) => k+': '+v).join('\n');
      const obs = get('id_observacoes'); if (!obs.value.includes(bloco)) obs.value = [obs.value, bloco].filter(Boolean).join('\n\n');
    }
    form.dispatchEvent(new Event('conta:atualizar'));
    resultado.hidden = true; mensagem(`${count} campo(s) aplicado(s). Confira o formulário e clique em Salvar.`);
  });
  get('captura-opcao').addEventListener('change', renderizar);
  get('captura-ler-codigo').addEventListener('click', () => lerCodigo(get('captura-codigo')));
  get('captura-ler-arquivo').addEventListener('click', lerArquivo);
  get('captura-cancelar').addEventListener('click', () => {encerrar(); mensagem('Leitura cancelada. Nenhum campo foi alterado.');});
  get('captura-arquivo').addEventListener('change', () => {encerrar(); resultado.hidden = true; arquivoLido = null; mensagem('Arquivo selecionado. Clique em Ler documento.');});
  const entradas = [[get('captura-codigo'),'auto'], [get('id_codigo_boleto'),'boleto'], [get('id_pix_copia_cola'),'pix']];
  for (const [input, tipo] of entradas) {
    input.addEventListener('keydown', e => {if (e.key === 'Enter' && !e.shiftKey) {e.preventDefault(); clearTimeout(timer); lerCodigo(input, tipo);}});
    input.addEventListener('input', () => {
      encerrar(); resultado.hidden = true; mensagem('');
      const valor = input.value.trim(), digitos = valor.replace(/[.\s-]/g, '');
      const completo = /^[0-9]+$/.test(digitos) && [44,47,48].includes(digitos.length);
      if (completo || (valor.startsWith('000201') && /6304[0-9a-fA-F]{4}$/.test(valor))) timer = setTimeout(() => lerCodigo(input,tipo), 500);
    });
  }
  get('processar-boleto').addEventListener('click', () => lerCodigo(get('id_codigo_boleto'),'boleto'));
  get('id_ciclo_boleto').addEventListener('change', () => {encerrar(); resultado.hidden = true; mensagem('Ciclo alterado. Leia o código novamente para atualizar as sugestões.');});
})();
