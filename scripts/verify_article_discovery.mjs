// Render generated pages with external traffic blocked. No publishing APIs.
import assert from 'node:assert/strict';
import http from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve,extname} from 'node:path';
import {createRequire} from 'node:module';
const {chromium}=createRequire('/tmp/ws-browser-check/package.json')('playwright');
const root=resolve('_site'),out=resolve('article-discovery-browser');
await mkdir(out,{recursive:true});
const mime={'.html':'text/html','.css':'text/css','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.png':'image/png','.jpg':'image/jpeg'};
const server=http.createServer(async(req,res)=>{
 try{
  const path=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  if(path==='/__verification-font.ttf'){
   res.setHeader('Content-Type','font/ttf');res.end(await readFile(resolve('assets/fonts/NotoSansJP.ttf')));return;
  }
  const file=resolve(root,'.'+path+(path.endsWith('/')?'index.html':''));
  if(!file.startsWith(root+'/'))throw Error();
  res.setHeader('Content-Type',mime[extname(file)]||'application/octet-stream');res.end(await readFile(file));
 }catch{res.statusCode=404;res.end('not found');}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
let browser;
try{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',args:['--no-sandbox']});
 const base='http://127.0.0.1:'+server.address().port;
 const feed=JSON.parse(await readFile(root+'/data/articles.json','utf8'));
 const sample=[feed.find(a=>a.category==='SECURITY'),feed.find(a=>a.category==='経済'),feed.find(a=>a.category==='マネジメント')];
 const results=[];
 for(const width of [390,1440])for(const article of sample){
  const page=await browser.newPage({viewport:{width,height:950},deviceScaleFactor:1});
  await page.route('**/*',r=>r.request().url().startsWith(base+'/')?r.continue():r.abort());
  await page.goto(base+'/articles/'+article.id+'/',{waitUntil:'networkidle'});
  // The CI image lacks Japanese system fonts and external traffic is blocked.
  // Use the repository's licensed Noto font for accurate Japanese layout QA.
  await page.addStyleTag({content:"@font-face{font-family:'Noto Sans JP';src:url('/__verification-font.ttf') format('truetype');font-weight:100 900;font-display:block}"});
  await page.evaluate(async()=>{await document.fonts.load("16px 'Noto Sans JP'");await document.fonts.ready;});
  const result=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,
   links:document.querySelectorAll('.article-reading-rail li a').length,
   author:document.querySelector('.article-byline')?.innerText,
   breadcrumb:document.querySelector('.article-breadcrumbs')?.innerText}));
  assert(!result.overflow,article.id+' overflows '+width);assert.equal(result.links,4);
  assert(result.author.includes('WORK SIGNAL編集部'));assert(result.breadcrumb.includes('ホーム'));
  await page.screenshot({path:out+'/'+article.id+'-'+width+'.png'});
  await page.locator('.article-reading-rail').screenshot({path:out+'/'+article.id+'-'+width+'-rail.png'});
  results.push({article_id:article.id,width,...result});await page.close();
 }
 for(const width of [390,1440]){
  const page=await browser.newPage({viewport:{width,height:950},deviceScaleFactor:1});
  await page.route('**/*',r=>r.request().url().startsWith(base+'/')?r.continue():r.abort());
  await page.goto(base+'/follow/',{waitUntil:'networkidle'});
  await page.addStyleTag({content:"@font-face{font-family:'Noto Sans JP';src:url('/__verification-font.ttf') format('truetype');font-weight:100 900;font-display:block}"});
  await page.evaluate(async()=>{await document.fonts.load("16px 'Noto Sans JP'");await document.fonts.ready;});
  assert.equal(await page.locator('[data-social-follow]').count(),3);
  assert.equal(await page.locator('form').count(),0);
  await page.context().grantPermissions(['clipboard-read','clipboard-write']);
  await page.locator('[data-copy-rss-url]').click();
  await page.waitForFunction(()=>document.querySelector('[data-rss-feedback]').textContent.includes('コピーしました'));
  assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),'https://signal.amberlight.co.jp/feed.xml');
  assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
  await page.screenshot({path:out+'/follow-'+width+'.png',fullPage:true});
  await page.goto(base+'/',{waitUntil:'networkidle'});
  assert.equal(await page.locator('.subscribe-strip a[href="/follow/"]').count(),1);
  assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
  results.push({page:'follow-and-home',width,overflow:false,channels:3,rss_copy:true});await page.close();
 }
 await import('node:fs/promises').then(fs=>fs.writeFile(out+'/results.json',JSON.stringify(results,null,2)));
 console.log('ARTICLE_DISCOVERY_BROWSER_OK',JSON.stringify(results));
}finally{await browser?.close();await new Promise(r=>server.close(r));}
