import {referenceRows,resultMetrics} from './model.mjs';
import {initCourtMotion} from './court-motion.mjs';
export function initNbaPage({teams=[],sets=[],sample=false}={}){
const TEAMS=teams,SETS=sets;
const team=code=>TEAMS.find(t=>t.code===code),game=id=>SETS.flat().find(g=>g.id===id);
const $=selector=>document.querySelector(selector);
const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
const reduced=matchMedia('(prefers-reduced-motion: reduce)'),fine=matchMedia('(hover: hover) and (pointer: fine)');
let set=0,conference='East',expanded=false,receiptTimer,opener=null,previousOverflow='';
const dialog=$('#game-dialog'),reception=$('#reception');
function renderResults(){
 if(!SETS.length){
  $('#set-label').textContent='NO RESULTS';$('#previous-set').disabled=true;$('#next-set').disabled=true;
  $('.edition-picker').hidden=true;
  $('#match-list').replaceChildren(node('p','data-empty','現在、試合結果を表示できません。'));
  return;
 }
 $('#set-label').textContent=`SET ${String(set+1).padStart(2,'0')} / ${String(SETS.length).padStart(2,'0')}`;
 $('#previous-set').disabled=set===0;$('#next-set').disabled=set===SETS.length-1;
 $('#match-list').replaceChildren(...SETS[set].map((g,i)=>{
  const b=node('button','match-row');b.type='button';b.dataset.game=g.id;
  b.setAttribute('aria-label',`${sample?'架空の試合 ':''}${g.home} ${g.homeScore}対${g.away} ${g.awayScore} の詳細を受信`);
  b.append(node('span','match-index',String(i+1).padStart(2,'0')));
  const names=node('span'),codes=node('span','match-teams');codes.append(node('b','',g.home),node('small','','vs'),node('b','',g.away));
  names.append(codes,node('span','match-names',`${team(g.home).name} / ${team(g.away).name}`));
  const score=node('span','match-score');score.append(document.createTextNode(g.homeScore),node('span','','—'),document.createTextNode(g.awayScore));
  const arrow=node('span','match-arrow','↗');arrow.setAttribute('aria-hidden','true');b.append(names,score,arrow);return b;
 }));
}
function renderStandings(){
 $('#conference-label').textContent=conference==='East'?'EASTERN CONFERENCE':'WESTERN CONFERENCE';
 $('#conference-letter').textContent=conference==='East'?'E':'W';
 const rows=referenceRows(TEAMS,conference);
 if(!rows.length){
  $('.conference-picker').hidden=true;$('#conference-label').textContent='STANDINGS';$('#conference-letter').textContent='—';
  const tr=node('tr'),td=node('td','data-empty','現在、順位情報を表示できません。');td.colSpan=6;tr.append(td);$('#standings-body').replaceChildren(tr);$('#expand-table').hidden=true;return;
 }
 $('#standings-body').replaceChildren(...rows.slice(0,expanded?15:6).map(t=>{
  const tr=node('tr');tr.dataset.team=t.code;
  const name=node('td','',t.name);name.append(node('small','',t.code));
  const rate=node('td','rate-cell'),bar=node('span','win-bar'),fill=node('i');bar.setAttribute('aria-hidden','true');bar.style.setProperty('--rate',`${Math.round(t.pct*100)}%`);bar.append(fill);rate.append(bar);
  tr.append(node('td','',t.rank===null?'—':String(t.rank).padStart(2,'0')),name,node('td','',t.wins),node('td','',t.losses),node('td','pct',t.pct===null?'—':t.pct.toFixed(3)),rate);return tr;
 }));
 document.querySelectorAll('[data-conference]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.conference===conference)));
 $('#expand-table').setAttribute('aria-expanded',String(expanded));$('#expand-table').replaceChildren(document.createTextNode(expanded?'上位6チームに戻す':'全15チームを表示'),node('span','',expanded?'−':'＋'));
}
function cancelReceipt(){clearTimeout(receiptTimer);reception.hidden=true;}
function receive(id,trigger){
 const g=game(id);if(!g||dialog.open)return;const metrics=resultMetrics(g);if(!metrics)return;
 cancelReceipt();opener=trigger;reception.hidden=false;
 receiptTimer=setTimeout(()=>{
  reception.hidden=true;
  $('#detail-title').replaceChildren(document.createTextNode(g.home),node('span','','vs'),document.createTextNode(g.away));
  $('#detail-score').replaceChildren(document.createTextNode(g.homeScore),node('span','','—'),document.createTextNode(g.awayScore));
  $('#detail-teams').replaceChildren(node('span','',team(g.home).name),node('span','',team(g.away).name));
  $('#detail-metrics').replaceChildren(...[['WINNER',metrics.winner],['MARGIN',`+${metrics.margin}`],['TOTAL POINTS',metrics.total]].map(([label,value])=>{const dl=node('dl');dl.append(node('dt','',label),node('dd','',value));return dl;}));
  previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden';dialog.showModal();$('.detail-close').focus({preventScroll:true});
 },reduced.matches?160:420);
}
$('#previous-set').addEventListener('click',()=>{set=Math.max(0,set-1);renderResults();});
$('#next-set').addEventListener('click',()=>{set=Math.min(SETS.length-1,set+1);renderResults();});
for(const button of document.querySelectorAll('[data-conference]'))button.addEventListener('click',()=>{conference=button.dataset.conference;expanded=false;renderStandings();});
$('#conference-label').setAttribute('aria-live','polite');$('#expand-table').setAttribute('aria-controls','standings-body');
$('#expand-table').addEventListener('click',()=>{expanded=!expanded;renderStandings();});
document.addEventListener('click',e=>{const b=e.target.closest('[data-game]');if(b)receive(b.dataset.game,b);});
$('.detail-close').addEventListener('click',()=>dialog.close());$('.detail-done').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',e=>{if(e.target!==dialog)return;const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();});
dialog.addEventListener('keydown',e=>{
 if(e.key!=='Tab')return;
 const first=$('.detail-close'),last=$('.detail-done');
 if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
 else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
});
dialog.addEventListener('close',()=>{document.body.style.overflow=previousOverflow;(opener?.isConnected?opener:$('.featured-match')).focus({preventScroll:true});});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!reception.hidden){cancelReceipt();opener?.isConnected&&opener.focus({preventScroll:true});}});
const arena=$('.arena-art'),courtMotion=initCourtMotion($('.court-drawing'),$('#court-pause'),reduced);let frame=0,pointer=[0,0],inView=true;
const resetArena=()=>{pointer=[0,0];arena.style.setProperty('--px',0);arena.style.setProperty('--py',0);};
arena.addEventListener('pointermove',e=>{if(!fine.matches||reduced.matches||e.pointerType!=='mouse')return;const r=arena.getBoundingClientRect();pointer=[Math.max(-1,Math.min(1,(e.clientX-r.left)/r.width*2-1)),Math.max(-1,Math.min(1,(e.clientY-r.top)/r.height*2-1))];if(!frame)frame=requestAnimationFrame(()=>{arena.style.setProperty('--px',pointer[0].toFixed(3));arena.style.setProperty('--py',pointer[1].toFixed(3));frame=0;});},{passive:true});
arena.addEventListener('pointerleave',resetArena);reduced.addEventListener('change',resetArena);
const syncMotion=()=>{courtMotion.setVisible(!document.hidden&&inView);};
if('IntersectionObserver'in window)new IntersectionObserver(([e])=>{inView=e.isIntersecting;syncMotion();}).observe(arena);
document.addEventListener('visibilitychange',()=>{syncMotion();if(document.hidden)cancelReceipt();});
addEventListener('pagehide',()=>{courtMotion.setVisible(false);cancelReceipt();cancelAnimationFrame(frame);frame=0;resetArena();if(dialog.open)dialog.close();});
addEventListener('pageshow',syncMotion);
const feature=SETS.flat()[0],featured=$('.featured-match');
if(feature){
 featured.hidden=false;$('.featured-pending')?.setAttribute('hidden','');featured.dataset.game=feature.id;
 featured.setAttribute('aria-label',`${sample?'架空の試合 ':''}${feature.home} ${feature.homeScore}対${feature.away} ${feature.awayScore} の詳細を受信`);
 const home=node('span','featured-team'),away=node('span','featured-team away'),score=node('span','featured-score'),hint=node('span','receive-hint','RECEIVE SIGNAL '),arrow=node('i','','↗');arrow.setAttribute('aria-hidden','true');hint.append(arrow);
 home.append(node('b','',feature.home),node('small','',team(feature.home).name));away.append(node('b','',feature.away),node('small','',team(feature.away).name));score.append(document.createTextNode(feature.homeScore),node('span','score-divider',':'),document.createTextNode(feature.awayScore));featured.replaceChildren(home,score,away,hint);
}else{featured.hidden=true;$('.featured-pending')?.removeAttribute('hidden');}
renderResults();renderStandings();syncMotion();
}
