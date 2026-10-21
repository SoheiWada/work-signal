// Server-side only. Only the free Teams and Games endpoints are allowed.
const ORIGIN='https://api.balldontlie.io';
const TYPES=['regular','ist','playin','playoffs'];
const STATES=new Set(['scheduled','in_progress','final','postponed','canceled','delayed','suspended','abandoned','unknown']);
const CUP=new Set(['Championship',...['East','West'].flatMap(c=>['Group A','Group B','Group C','Quarterfinal','Semifinal'].map(s=>`${c} ${s}`))]);
const fail=code=>{throw new Error(code)};
const integer=n=>Number.isSafeInteger(n)&&n>=0;
const day=s=>typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&!Number.isNaN(Date.parse(s+'T12:00:00Z'))&&new Date(s+'T12:00:00Z').toISOString().slice(0,10)===s;
export function nbaDate(now=new Date()){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
 const get=t=>parts.find(p=>p.type===t).value;return `${get('year')}-${get('month')}-${get('day')}`;
}
export function currentSeason(now=new Date()){const d=nbaDate(now);return Number(d.slice(0,4))-(Number(d.slice(5,7))<10?1:0)}
export async function collectNba({apiKey,now=new Date(),season=currentSeason(now),fetcher=fetch,wait=ms=>new Promise(r=>setTimeout(r,ms))}={}){
 if(typeof apiKey!=='string'||!apiKey.trim())fail('missing_key');
 if(!Number.isInteger(season)||season<2025||season>currentSeason(now))fail('invalid_season');
 const throughDate=nbaDate(now);let requests=0;
 async function get(path,params={}){
  if(!['/nba/v1/teams','/nba/v1/games'].includes(path))fail('endpoint_not_allowed');
  if(requests>=50)fail('request_budget_exceeded');
  if(requests)await wait(15000);requests++;
  const url=new URL(path,ORIGIN);for(const [k,v]of Object.entries(params))url.searchParams.set(k,String(v));
  let response;try{response=await fetcher(url,{headers:{Authorization:apiKey.trim(),Accept:'application/json'},redirect:'error',signal:AbortSignal.timeout(15000)})}catch{fail('network_error')}
  if(!response.ok)fail(response.status===429?'rate_limited':[401,403].includes(response.status)?'access_denied':'provider_error');
  const body=await response.text();if(body.length>2000000)fail('response_too_large');
  let value;try{value=JSON.parse(body)}catch{fail('invalid_response')}
  if(!value||!Array.isArray(value.data)||value.data.length>100)fail('invalid_response');
  if(path==='/nba/v1/teams'&&!value.meta)value.meta={next_cursor:null};
  if(!value.meta)fail('invalid_pagination');
  if(!Object.hasOwn(value.meta,'next_cursor')){if(value.meta.per_page===100&&value.data.length<100)value.meta.next_cursor=null;else fail('invalid_pagination')}
  return value;
 }
 async function pages(path,params){
  const values=[],seen=new Set();let cursor;
  do{
   const response=await get(path,{...params,per_page:100,...(cursor===undefined?{}:{cursor})});values.push(...response.data);
   const next=response.meta.next_cursor;
   if(next===null){cursor=undefined;break}
   if(!integer(next)||seen.has(next)||response.data.length===0)fail('invalid_pagination');seen.add(next);cursor=next;
  }while(true);
  return values;
 }
 const rawTeams=await pages('/nba/v1/teams',{}),teams=rawTeams.filter(t=>integer(t.id)&&t.id>=1&&t.id<=30).map(t=>{
  if(!['East','West'].includes(t.conference)||typeof t.abbreviation!=='string'||! /^[A-Z]{2,4}$/.test(t.abbreviation)||typeof t.full_name!=='string'||!t.full_name.trim()||t.full_name.length>100)fail('invalid_team');
  return {id:t.id,code:t.abbreviation,name:t.full_name,conference:t.conference,wins:0,losses:0};
 });
 if(teams.length!==30||new Set(teams.map(t=>t.id)).size!==30||new Set(teams.map(t=>t.code)).size!==30||teams.filter(t=>t.conference==='East').length!==15)fail('incomplete_teams');
 const byId=new Map(teams.map(t=>[t.id,t])),games=new Map();let unknownRegular=0;
 for(const type of TYPES){
  const raw=await pages('/nba/v1/games',{'seasons[]':season,season_type:type,end_date:throughDate});
  const ids=new Set();
  for(const g of raw){
   if(!integer(g.id)||g.id===0||ids.has(g.id)||g.season!==season||!day(g.date)||g.date>throughDate||!byId.has(g.home_team?.id)||!byId.has(g.visitor_team?.id)||g.home_team.id===g.visitor_team.id||!STATES.has(g.status_state)||typeof g.postseason!=='boolean')fail('invalid_game');ids.add(g.id);
   if(['regular','ist'].includes(type)&&g.postseason)fail('invalid_season_type');
   if(!Object.hasOwn(g,'ist_stage')||(g.ist_stage!==null&&!CUP.has(g.ist_stage)))fail('unknown_cup_stage');
   if(g.status_state!=='final'){
    if(['regular','ist'].includes(type)&&g.status_state==='unknown')unknownRegular++;
    continue;
   }
   if(g.postponed===true||!integer(g.home_team_score)||!integer(g.visitor_team_score)||g.home_team_score===g.visitor_team_score||g.home_team_score===0||g.visitor_team_score===0||g.home_team_score>1000||g.visitor_team_score>1000)fail('invalid_final_score');
   const counts=['regular','ist'].includes(type)&&g.ist_stage!=='Championship';
   const game={id:String(g.id),date:g.date,home:byId.get(g.home_team.id).code,away:byId.get(g.visitor_team.id).code,homeScore:g.home_team_score,awayScore:g.visitor_team_score,competition:type==='ist'?'cup':type,countsForStandings:counts};
   const prior=games.get(game.id);
   if(prior){
    if(['date','home','away','homeScore','awayScore','countsForStandings'].some(k=>prior[k]!==game[k]))fail('conflicting_duplicate');
    if(type==='ist')prior.competition='cup';
   }else games.set(game.id,game);
  }
 }
 const final=[...games.values()].sort((a,b)=>b.date.localeCompare(a.date)||Number(b.id)-Number(a.id));
 const byCode=new Map(teams.map(t=>[t.code,t]));let counted=0;
 for(const g of final.filter(g=>g.countsForStandings)){
  counted++;const home=byCode.get(g.home),away=byCode.get(g.away);home[g.homeScore>g.awayScore?'wins':'losses']++;away[g.awayScore>g.homeScore?'wins':'losses']++;
 }
 if(teams.some(t=>t.wins+t.losses>82)||teams.reduce((n,t)=>n+t.wins,0)!==counted||teams.reduce((n,t)=>n+t.losses,0)!==counted)fail('invalid_aggregate');
 const standingsAvailable=counted>0&&unknownRegular===0;
 if(!standingsAvailable)for(const t of teams){t.wins=null;t.losses=null}
 const dates=[...new Set(final.map(g=>g.date))].slice(0,7);
 return {version:1,provider:'balldontlie',season,throughDate,fetchedAt:now.toISOString(),lastAttemptAt:now.toISOString(),refreshState:'ok',paginationComplete:true,standingsAvailable,countedGames:counted,standingsReason:standingsAvailable?null:unknownRegular?'unknown_game_status':'no_final_games',teams:teams.map(({id,...t})=>t),sets:dates.map(d=>final.filter(g=>g.date===d)),requests};
}
export function failedSnapshot(previous,error,now=new Date()){
 const allowed=new Set(['missing_key','invalid_season','request_budget_exceeded','network_error','rate_limited','access_denied','provider_error','response_too_large','invalid_response','invalid_pagination','invalid_team','incomplete_teams','invalid_game','invalid_season_type','unknown_cup_stage','invalid_final_score','conflicting_duplicate','invalid_aggregate']);
 const code=allowed.has(error?.message)?error.message:'refresh_failed';
 const empty={version:1,provider:'balldontlie',fetchedAt:null,teams:[],sets:[],standingsAvailable:false};
 const fields=['version','provider','season','throughDate','fetchedAt','paginationComplete','standingsAvailable','countedGames','standingsReason','teams','sets','requests'];
 const base=previous?.version===1&&previous?.provider==='balldontlie'?Object.fromEntries(fields.filter(k=>Object.hasOwn(previous,k)).map(k=>[k,previous[k]])):empty;
 return {...base,lastAttemptAt:now.toISOString(),refreshState:code==='missing_key'&&!base.fetchedAt?'unconfigured':'error',lastError:code};
}
