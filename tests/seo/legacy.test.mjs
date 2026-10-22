import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';
// Exercise the actual compatibility script without a browser or network.
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.attrs={};this._text='';this.className='';this.classList={add:name=>{this.className+=' '+name;}};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;this._text='';}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(n=>typeof n==='string'?n:n.textContent).join('');}
  setAttribute(k,v){this.attrs[k]=v;}
  addEventListener(){}
  querySelectorAll(selector){return this.children.flatMap(n=>typeof n==='string'?[]:[...(selector==='section.block'&&n.tag==='section'&&n.className==='block'?[n]:[]),...n.querySelectorAll(selector)]);}
}
const template=readFileSync(new URL('../../article.html',import.meta.url),'utf8');
const feed=JSON.parse(readFileSync(new URL('../../data/articles.json',import.meta.url),'utf8'));
const code=[...template.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n');
async function render(id,items=feed){
  const root=new Element('main'),head=new Element('head'),description=new Element('meta');
  const document={head,title:'ARTICLE — WORK SIGNAL',createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),createTextNode:text=>String(text),querySelector:selector=>selector==='#article'?root:selector==='meta[name="description"]'?description:null};
  const context={document,location:{search:'?id='+encodeURIComponent(id)},URLSearchParams,Intl,console,window:{},fetch:async()=>({ok:true,json:async()=>items})};context.window=context;
  vm.runInNewContext(code,context);await new Promise(resolve=>setImmediate(resolve));return {root,head,document};
}
test('all published legacy URLs retain every section and the canonical URL',async()=>{
  for(const article of feed){
    const {root,head,document}=await render(article.id);assert.equal(document.title,article.title+' — WORK SIGNAL',article.id);
    for(const section of article.sections||[]){if(section.title&&section.body){assert.ok(root.textContent.includes(section.title),article.id);for(const paragraph of section.body.split(/\n\s*\n/).filter(Boolean))assert.ok(root.textContent.includes(paragraph),article.id+': missing body');}}
    assert.ok(head.children.some(n=>n.rel==='canonical'&&n.href==='https://signal.amberlight.co.jp/articles/'+article.id+'/'),article.id);
  }
});
test('unknown and draft URLs remain unavailable',async()=>{
  for(const [id,items] of [['not-published',feed],['draft-only',[{...feed[0],id:'draft-only',status:'draft'}]]]){
    const {root,head}=await render(id,items);assert.ok(root.textContent.includes('NO SIGNAL.'));assert.ok(head.children.some(n=>n.name==='robots'&&n.content==='noindex'));
  }
});
