import test from 'node:test';
import assert from 'node:assert/strict';
import {collectNba,failedSnapshot,currentSeason,nbaDate} from '../../services/nba-data/collector.mjs';
import {parseNbaSnapshot} from '../../nba/feed.mjs';
const now=new Date('2026-12-20T12:00:00Z');
const teams=Array.from({length:30},(_,i)=>({id:i+1,abbreviation:`${i<15?'E':'W'}${String.fromCharCode(65+i%15)}`,full_name:`Test team ${i+1}`,conference:i<15?'East':'West'}));
const game=(id,home=1,away=16,more={})=>({id,date:'2026-12-18',season:2026,status:'Final',status_state:'final',postseason:false,postponed:false,ist_stage:null,home_team_score:110,visitor_team_score:100,home_team:{id:home},visitor_team:{id:away},...more});
function provider(series={},override){
 const calls=[],waits=[];
 const fetcher=async(url,options)=>{
  calls.push({url:new URL(url),options});
  if(override){const r=override(url,calls.length);if(r)return r}
  if(url.pathname.endsWith('/teams'))return new Response(JSON.stringify({data:teams}));
  const type=url.searchParams.get('season_type');const rows=series[type]||[];
  return new Response(JSON.stringify({data:rows,meta:{per_page:100,next_cursor:null}}));
 };
 return {calls,waits,fetcher,wait:async(ms)=>waits.push(ms)};
}
const run=(p,more={})=>collectNba({apiKey:'test-key-never-public',now,fetcher:p.fetcher,wait:p.wait,...more});
test('only final games are displayed; NBA Cup final, play-in and playoffs never affect regular-season wins',async()=>{
 const common=game(1);
 const p=provider({regular:[common,game(2,2,17,{status_state:'in_progress',status:'4th Qtr'})],ist:[common,game(3,3,18,{ist_stage:'Championship'})],playin:[game(4,4,19)],playoffs:[game(5,5,20,{postseason:true})]});
 const result=await run(p);
 assert.equal(result.countedGames,1);assert.equal(result.sets.flat().length,4);assert.equal(result.teams[0].wins,1);assert.equal(result.teams[2].wins,0);
 assert.equal(result.sets.flat().find(g=>g.id==='1').competition,'cup');
 assert.equal(result.sets.flat().find(g=>g.id==='3').countsForStandings,false);
 assert.equal(p.calls.length,5);assert.deepEqual(p.waits,[15000,15000,15000,15000]);
 for(const call of p.calls){assert.equal(call.url.origin,'https://api.balldontlie.io');assert.ok(['/nba/v1/teams','/nba/v1/games'].includes(call.url.pathname));assert.equal(call.options.redirect,'error');assert.equal(call.options.headers.Authorization,'test-key-never-public')}
 assert.ok(!JSON.stringify(result).includes('test-key-never-public'));
 const parsed=parseNbaSnapshot(result,now.getTime());assert.equal(parsed.feed.state,'fresh');assert.equal(parsed.teams.length,30);
});
test('authentication, throttling and partial pagination stop rather than publishing partial standings',async()=>{
 for(const status of [401,403,429,500]){
  const p=provider({},()=>new Response('{}',{status}));await assert.rejects(run(p),new RegExp(status===429?'rate_limited':status===500?'provider_error':'access_denied'));assert.equal(p.calls.length,1);
 }
 const p=provider({},url=>url.pathname.endsWith('/games')?new Response(JSON.stringify({data:[game(1)],meta:{next_cursor:1,per_page:100}})):null);
 await assert.rejects(run(p),/invalid_pagination|invalid_game/);
 const partial=provider({},url=>url.pathname.endsWith('/games')?new Response(JSON.stringify({data:[game(1)]})):null);
 await assert.rejects(run(partial),/invalid_pagination/);
});
test('follows cursors to completion; duplicate or conflicting records are not silently counted twice',async()=>{
 const p=provider({},url=>{
  if(!url.pathname.endsWith('/games')||url.searchParams.get('season_type')!=='regular')return;
  return new Response(JSON.stringify(url.searchParams.has('cursor')?{data:[game(2,2,17)],meta:{per_page:100}}:{data:[game(1)],meta:{per_page:100,next_cursor:9}}));
 });
 const result=await run(p);assert.equal(result.countedGames,2);assert.equal(p.calls.length,6);
 const conflict=provider({regular:[game(1)],ist:[game(1,1,16,{home_team_score:112})]});await assert.rejects(run(conflict),/conflicting_duplicate/);
});
test('invalid season classification, final scores and incomplete teams fail closed',async()=>{
 for(const change of [{home_team_score:100},{visitor_team_score:-1},{postponed:true},{postseason:true},{ist_stage:'Unclassified final'},{season:2025},{date:'2026-12-99'},{home_team:{id:99}}]){
  await assert.rejects(run(provider({regular:[game(1,1,16,change)]})));
 }
 const p=provider({},url=>url.pathname.endsWith('/teams')?new Response(JSON.stringify({data:teams.slice(1)})):null);await assert.rejects(run(p),/incomplete_teams/);
});
test('unknown regular-season status withholds reference standings; zero completed games never invent records',async()=>{
 const result=await run(provider({regular:[game(1),game(2,2,17,{status_state:'unknown'})]}));assert.equal(result.standingsAvailable,false);assert.equal(result.standingsReason,'unknown_game_status');assert.ok(result.teams.every(t=>t.wins===null));assert.equal(result.sets.flat().length,1);
 const empty=await run(provider());assert.equal(empty.standingsAvailable,false);assert.equal(empty.sets.length,0);assert.ok(empty.teams.every(t=>t.wins===null));
});
test('missing key makes no network request and failure retains last successful data with an explicit error state',async()=>{
 const p=provider();await assert.rejects(run(p,{apiKey:''}),/missing_key/);assert.equal(p.calls.length,0);
 const good=await run(provider({regular:[game(1)]}));const failed=failedSnapshot(good,new Error('network_error'),new Date('2026-12-21T12:00:00Z'));
 assert.equal(failed.fetchedAt,good.fetchedAt);assert.deepEqual(failed.sets,good.sets);assert.equal(failed.refreshState,'error');assert.equal(parseNbaSnapshot(failed,Date.parse(failed.lastAttemptAt)).feed.state,'error');
 assert.equal(failedSnapshot(null,new Error('missing_key'),now).refreshState,'unconfigured');
});
test('snapshot parser detects stale data, future clocks, invalid references and forged scores',async()=>{
 const good=await run(provider({regular:[game(1)]}));assert.equal(parseNbaSnapshot(good,now.getTime()+27*3600000).feed.state,'stale');
 assert.throws(()=>parseNbaSnapshot({...good,fetchedAt:'2029-01-01T00:00:00Z'},now.getTime()));
 const broken=structuredClone(good);broken.sets[0][0].away='ZZZ';assert.throws(()=>parseNbaSnapshot(broken,now.getTime()));
 const negative=structuredClone(good);negative.sets[0][0].homeScore=-1;assert.throws(()=>parseNbaSnapshot(negative,now.getTime()));
 assert.throws(()=>parseNbaSnapshot({...good,teams:good.teams.slice(1)},now.getTime()));
});
test('US Eastern dates and season rollover are explicit, independent of server timezone',()=>{
 assert.equal(nbaDate(new Date('2026-10-01T01:00:00Z')),'2026-09-30');assert.equal(currentSeason(new Date('2026-10-01T01:00:00Z')),2025);assert.equal(currentSeason(new Date('2026-10-01T12:00:00Z')),2026);
});

test('the hard request budget prevents an endless or unexpectedly large feed from running indefinitely',async()=>{
 const p=provider({},(url,call)=>{
  if(!url.pathname.endsWith('/games'))return;
  return new Response(JSON.stringify({data:[game(call)],meta:{per_page:100,next_cursor:call}}));
 });
 await assert.rejects(run(p),/request_budget_exceeded/);assert.equal(p.calls.length,50);assert.equal(p.waits.length,49);
});
