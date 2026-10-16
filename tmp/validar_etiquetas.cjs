const {chromium}=require('C:/Users/Isabela/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {pathToFileURL}=require('url');const path=require('path');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const p=await browser.newPage();const erros=[];p.on('pageerror',e=>erros.push(e.message));let pedidos=[];
  const compartilhada='\\\\NEGRI\\REGISTER-Etiquetas';
  await p.route('http://127.0.0.1:17857/**',route=>{
   const request=route.request();
   if(request.method()==='OPTIONS')return route.fulfill({status:200,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Private-Network':'true'}});
   let result;
   if(request.url().endsWith('/status'))result={assistente:'REGISTER',versao:'raw30-multicomputador-2',impressoras:['POS-58',compartilhada],impressora:'POS-58'};
   else {const body=request.postDataJSON();pedidos.push(body);result={status:'enviada',impressora:body.impressora,trabalho:1};}
   return route.fulfill({json:result,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Private-Network':'true'}});
  });
  await p.goto(pathToFileURL(path.join(process.cwd(),'tmp/etiqueta-multicomputador.html')).href);
  await p.getByRole('button',{name:'Atualizar impressoras'}).click();
  await p.waitForFunction(()=>document.querySelector('#impressora-etiqueta').options.length===3);
  await p.selectOption('#impressora-etiqueta',compartilhada);
  await p.click('#imprimir');await p.waitForFunction(()=>document.querySelector('#impressao-status').textContent.includes('Etiqueta enviada'));
  if(pedidos.length!==1||pedidos[0].impressora!==compartilhada)throw Error('Destino incorreto');
  await p.reload();await p.getByRole('button',{name:'Atualizar impressoras'}).click();
  await p.waitForFunction(n=>document.querySelector('#impressora-etiqueta').value===n,compartilhada);
  await p.setViewportSize({width:390,height:850});await p.screenshot({path:'tmp/etiquetas-multicomputador-mobile.png',fullPage:true});
  if(erros.length)throw Error(erros.join('\n'));console.log('Seleção local/compartilhada, envio único e preferência por computador: OK');
 } finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
