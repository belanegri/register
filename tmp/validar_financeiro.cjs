const {chromium}=require('C:/Users/Isabela/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const path=require('path'); const {pathToFileURL}=require('url');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const pagina=await browser.newPage();
 const erros=[];pagina.on('pageerror',e=>erros.push(e.message));
 const base=path.join(process.cwd(),'tmp','financeiro-preview');
 for (const largura of [1440,390]) {
  await pagina.setViewportSize({width:largura,height:1000});
  for(const nome of ['receber','pagar','nova-receber','nova-pagar']) {
   await pagina.goto(pathToFileURL(path.join(base,nome+'.html')).href);
   await pagina.waitForLoadState('load');
   const excede=await pagina.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);
   if(excede) throw Error(nome+' extrapola a largura '+largura);
   if(nome==='receber'||nome==='pagar'){
    await pagina.locator('.acoes-conta').first().click();
    await pagina.getByRole('button',{name:'Visualização rápida',exact:true}).first().click();
    await pagina.locator('.modal.show').waitFor();
    await pagina.waitForFunction(()=>document.querySelector('.modal.show')?.getBoundingClientRect().height>0 && getComputedStyle(document.querySelector('.modal.show')).opacity==='1');
    await pagina.screenshot({path:path.join(base,nome+'-'+largura+'-previa.png')});
    await pagina.locator('.modal.show .btn-close').click();
   } else {
    if(nome==='nova-pagar') await pagina.locator('#id_modo').selectOption('parcelada');
    await pagina.locator('#id_valor_original').fill('100');
    await pagina.locator('#id_vencimento').fill('2027-01-31');
    await pagina.locator('#id_quantidade_lancamentos').fill('2');
    await pagina.locator('#id_entrada').fill('20');
    await pagina.locator('#id_data_entrada').fill('2027-01-15');
    await pagina.getByRole('button',{name:'Montar parcelas para ajustar',exact:true}).click();
    const plano=await pagina.locator('#id_plano_personalizado').inputValue();
    const linhas=plano.split('\n');
    if(linhas.length!==3||Number(linhas[0].split(';')[1])!==20||Number(linhas[2].split(';')[1])!==40) throw Error('Plano incorreto: '+plano);
    await pagina.screenshot({path:path.join(base,nome+'-'+largura+'.png'),fullPage:true});
   }
   console.log(nome,largura,'OK');
  }
 }
 if(erros.length) throw Error(erros.join('\n'));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
