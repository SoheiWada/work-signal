import {referenceRows,resultMetrics} from './model.mjs';
import {initCourtMotion} from './court-motion.mjs';
export function initNbaPage({teams=[],sets=[],sample=false}={}){
let TEAMS=teams,SETS=sets,feed=null;
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
 $('.edition-picker').hidden=false;
 $('#set-label').textContent=!sample&&SETS[set]?.[0]?.date?`${SETS[set][0].date.replaceAll('-','.')} / ET`:`SET ${String(set+1).padStart(2,'0')} / ${String(SETS.length).padStart(2,'0')}`;
 $('#previous-set').disabled=set===0;$('#next-set').disabled=set===SETS.length-1;
 $('#match-list').replaceChildren(...SETS[set].map((g,i)=>{
  const b=node('button','match-row');b.type='button';b.dataset.game=g.id;
  b.setAttribute('aria-label',`${sample?'架空の試合 ':g.date?g.date+'（米東部日付）確定結果 ':''}${g.home} ${g.homeScore}対${g.away} ${g.awayScore} の詳細を受信`);
  b.append(node('span','match-index',String(i+1).padStart(2,'0')));
  const names=node('span'),codes=node('span','match-teams');codes.append(node('b','',g.home),node('small','','vs'),node('b','',g.away));
  names.append(codes,node('span','match-names',`${!sample&&g.date?g.date+' ET · '+competition(g)+' / ':''}${team(g.home).name} / ${team(g.away).name}`));
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
 $('.conference-picker').hidden=false;$('#expand-table').hidden=false;
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
  if(!sample&&g.date)$('.detail-note').textContent=`${g.date}（米東部日付） / ${competition(g)} / 確定結果。${g.countsForStandings?'参考勝敗の集計対象。':'レギュラーシーズンの勝敗には算入しません。'} 最終取得 ${stamp(feed?.fetchedAt)}。提供: BALLDONTLIE（非公式集計）。`;
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
function renderFeature(){
const feature=SETS.flat()[0],featured=$('.featured-match');
if(feature){
 featured.hidden=false;$('.featured-pending')?.setAttribute('hidden','');featured.dataset.game=feature.id;
 featured.setAttribute('aria-label',`${sample?'架空の試合 ':feature.date?feature.date+'（米東部日付）確定結果 ':''}${feature.home} ${feature.homeScore}対${feature.away} ${feature.awayScore} の詳細を受信`);
 const home=node('span','featured-team'),away=node('span','featured-team away'),score=node('span','featured-score'),hint=node('span','receive-hint','RECEIVE SIGNAL '),arrow=node('i','','↗');arrow.setAttribute('aria-hidden','true');hint.append(arrow);
 home.append(node('b','',feature.home),node('small','',team(feature.home).name));away.append(node('b','',feature.away),node('small','',team(feature.away).name));score.append(document.createTextNode(feature.homeScore),node('span','score-divider',':'),document.createTextNode(feature.awayScore));featured.replaceChildren(home,score,away,hint);
}else{featured.hidden=true;$('.featured-pending')?.removeAttribute('hidden');}
}
function competition(g){return {regular:'REGULAR SEASON',cup:'NBA CUP',playin:'PLAY-IN',playoffs:'PLAYOFFS'}[g.competition]||'FINAL'}
function stamp(value){if(!value)return '未取得';return new Intl.DateTimeFormat('ja-JP',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value))+' JST'}
function renderFeed(){
 if(sample||!$('#nba-data-status'))return;
 const ready=Boolean(feed?.fetchedAt),problem=['error','stale'].includes(feed?.state);
 const message=ready?(problem?'更新が停止しています。最終取得分を表示しています。':'終了を確認した試合を表示。定期更新のためリアルタイムではありません。'):feed?.state==='unconfigured'?'データ接続の設定待ちです。':feed?.state==='error'?'試合データを取得できませんでした。':'データの接続状態を確認しています。';
 $('#nba-data-status').textContent=message;$('.data-provenance').classList.toggle('has-data-error',problem||feed?.state==='error');
 $('#nba-data-time').textContent=stamp(feed?.fetchedAt);$('#nba-data-attempt').textContent=stamp(feed?.lastAttemptAt);
 $('.study-notice span:nth-child(2)').textContent=ready?(problem?'更新停止 / 最終取得分':'終了確認分 / 定期更新'):'試合データは現在未接続です';
 $('.notice-end').textContent=ready?'FINAL RESULTS / NOT LIVE':'DATA PENDING';
 $('.featured-label span:last-child').textContent=SETS[0]?.[0]?.date?`${SETS[0][0].date} / FINAL`:ready?'NO FINAL RESULTS':'DATA PENDING';
 const pending=$('.featured-pending p');if(pending)pending.textContent=ready?'対象シーズンの終了試合はまだありません。':'試合データは現在未接続です。';
 $('.results-foot>span:first-child').textContent=ready?`${feed.season}–${String(feed.season+1).slice(-2)} / FINAL RESULTS`:'AWAITING VERIFIED RESULTS.';
 $('.table-meta>span:last-child').textContent=ready?`参考順位 / ${feed.season}–${String(feed.season+1).slice(-2)} / 終了確認分`:'順位情報 / 未取得';
 $('.table-note').textContent=ready?'取得済みのレギュラーシーズン終了試合を集計した参考成績です。NBAカップ決勝・プレーイン・プレーオフは勝敗から除外。同勝率は同順位とし、公式タイブレーク・公式シードは反映しません。提供元の欠損や訂正により公式成績と異なる場合があります。': '順位情報は未取得です。確認できるまで勝敗・勝率を表示しません。';
 $('.table-wrap caption').textContent=ready?'取得済み終了試合から集計したチームの勝敗・勝率と参考順位。公式順位ではありません。':'チームの勝敗・勝率。現在データを表示できません。';
 if(ready&&!SETS.length){const empty=$('#match-list .data-empty');if(empty)empty.textContent='対象シーズンの終了試合はまだありません。'}
 if(ready&&!feed.standingsAvailable){const empty=$('#standings-body .data-empty');if(empty)empty.textContent=feed.reason==='no_final_games'?'集計対象の終了試合はまだありません。':'試合状態を確認できないため、参考成績の集計を保留しています。'}
}
function updateData(value){
 if(dialog.open)dialog.close();cancelReceipt();const selectedDate=SETS[set]?.[0]?.date;TEAMS=value.teams;SETS=value.sets;feed=value.feed;set=Math.max(0,SETS.findIndex(group=>group[0]?.date===selectedDate));
 renderFeature();renderResults();renderStandings();renderFeed();
}
renderFeature();renderResults();renderStandings();renderFeed();syncMotion();
return {updateData};
}
