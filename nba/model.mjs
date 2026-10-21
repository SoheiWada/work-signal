// Reference sorting only: shared ranks for equal win rates. Never an official seed.
export function referenceRows(teams, conference) {
 const rows=teams.filter(t=>t.conference===conference&&Number.isSafeInteger(t.wins)&&t.wins>=0&&Number.isSafeInteger(t.losses)&&t.losses>=0)
  .map(t=>({...t,played:t.wins+t.losses}));
 rows.sort((a,b)=>{
  if(!a.played||!b.played)return Number(!a.played)-Number(!b.played)||a.code.localeCompare(b.code);
  return b.wins*a.played-a.wins*b.played||a.code.localeCompare(b.code);
 });
 let rank=null;
 return rows.map((t,i)=>{
  if(!t.played)return {...t,rank:null,pct:null};
  const prior=rows[i-1];
  if(!prior||t.wins*prior.played!==prior.wins*t.played)rank=i+1;
  return {...t,rank,pct:t.wins/t.played};
 });
}
export function resultMetrics(g) {
 if(!g||!Number.isSafeInteger(g.homeScore)||!Number.isSafeInteger(g.awayScore)||g.homeScore<0||g.awayScore<0||g.homeScore===g.awayScore)return null;
 return {winner:g.homeScore>g.awayScore?g.home:g.away,margin:Math.abs(g.homeScore-g.awayScore),total:g.homeScore+g.awayScore};
}
