// Public display snapshot only. No provider credentials or external API calls.
const validDate=s=>typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&!Number.isNaN(Date.parse(s+'T12:00:00Z'))&&new Date(s+'T12:00:00Z').toISOString().slice(0,10)===s;
const bad=()=>{throw new Error('Invalid NBA snapshot')};
export function parseNbaSnapshot(value,now=Date.now()){
 if(!value||value.version!==1||value.provider!=='balldontlie'||!['ok','error','unconfigured'].includes(value.refreshState)||!Array.isArray(value.teams)||!Array.isArray(value.sets))bad();
 const attempt=value.lastAttemptAt?Date.parse(value.lastAttemptAt):null;
 if(attempt!==null&&(!Number.isFinite(attempt)||attempt>now+300000))bad();
 if(!value.fetchedAt){if(value.teams.length||value.sets.length)bad();return {teams:[],sets:[],feed:{state:value.refreshState==='unconfigured'?'unconfigured':'error',fetchedAt:null,lastAttemptAt:value.lastAttemptAt??null}}}
 const fetched=Date.parse(value.fetchedAt);
 if(!Number.isFinite(fetched)||fetched>now+300000||!Number.isInteger(value.season)||value.season<2025||!validDate(value.throughDate)||value.paginationComplete!==true||typeof value.standingsAvailable!=='boolean'||value.teams.length!==30||value.sets.length>7)bad();
 const teams=value.teams.map(t=>{
  if(!t||!['East','West'].includes(t.conference)||typeof t.code!=='string'||!/^[A-Z]{2,4}$/.test(t.code)||typeof t.name!=='string'||!t.name.trim()||t.name.length>100)bad();
  if(value.standingsAvailable){if(!Number.isSafeInteger(t.wins)||!Number.isSafeInteger(t.losses)||t.wins<0||t.losses<0||t.wins+t.losses>82)bad()}
  else if(t.wins!==null||t.losses!==null)bad();
  return {code:t.code,name:t.name,conference:t.conference,wins:t.wins,losses:t.losses};
 });
 const codes=new Set(teams.map(t=>t.code)),ids=new Set(),days=new Set();
 if(codes.size!==30||teams.filter(t=>t.conference==='East').length!==15)bad();
 const sets=value.sets.map(set=>{
  if(!Array.isArray(set)||!set.length||set.length>30||!validDate(set[0]?.date)||days.has(set[0].date))bad();days.add(set[0].date);
  return set.map(g=>{
   if(!g||typeof g.id!=='string'||!/^\d+$/.test(g.id)||ids.has(g.id)||!codes.has(g.home)||!codes.has(g.away)||g.home===g.away||!validDate(g.date)||g.date!==set[0].date||g.date>value.throughDate||!['regular','cup','playin','playoffs'].includes(g.competition)||typeof g.countsForStandings!=='boolean'||!Number.isSafeInteger(g.homeScore)||!Number.isSafeInteger(g.awayScore)||g.homeScore<=0||g.awayScore<=0||g.homeScore>1000||g.awayScore>1000||g.homeScore===g.awayScore)bad();ids.add(g.id);
   return {id:g.id,date:g.date,home:g.home,away:g.away,homeScore:g.homeScore,awayScore:g.awayScore,competition:g.competition,countsForStandings:g.countsForStandings};
  });
 });
 return {teams,sets,feed:{state:value.refreshState==='error'?'error':now-fetched>26*3600000?'stale':'fresh',fetchedAt:value.fetchedAt,lastAttemptAt:value.lastAttemptAt,season:value.season,throughDate:value.throughDate,standingsAvailable:value.standingsAvailable,countedGames:value.countedGames,reason:value.standingsReason}};
}
