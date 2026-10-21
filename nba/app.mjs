import {initNbaPage} from './page.mjs?v=20261021-data';
import {parseNbaSnapshot} from './feed.mjs';
const page=initNbaPage();let last=null,checked=0,busy=false;
async function refresh(){
 if(busy||document.hidden||document.querySelector('#game-dialog')?.open||document.activeElement?.closest('[data-game]'))return;busy=true;checked=Date.now();
 try{
  const response=await fetch(new URL('./data.json',import.meta.url),{cache:'no-cache',credentials:'omit',redirect:'error',signal:AbortSignal.timeout(8000)});
  if(!response.ok)throw new Error('Snapshot unavailable');
  const text=await response.text();if(text.length>250000)throw new Error('Snapshot too large');
  const candidate=parseNbaSnapshot(JSON.parse(text));if(document.querySelector('#game-dialog')?.open)return;last=candidate;page.updateData(last);
 }catch{
  if(document.querySelector('#game-dialog')?.open)return;
  page.updateData(last?{...last,feed:{...last.feed,state:'error'}}:{teams:[],sets:[],feed:{state:'error',fetchedAt:null}});
 }finally{busy=false}
}
refresh();
setInterval(refresh,30*60000);
// A returning tab refreshes the shared static snapshot; never the provider API.
addEventListener('visibilitychange',()=>{if(!document.hidden&&Date.now()-checked>30*60000)refresh()});
