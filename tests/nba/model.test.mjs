import test from 'node:test';
import assert from 'node:assert/strict';
import {referenceRows,resultMetrics} from '../../nba/model.mjs';
import {TEAMS,SETS} from '../../prototypes/nba-signal/data.mjs';
test('reference ranks preserve ties across different games played, with zero-game teams unranked',()=>{
 const t=(code,wins,losses)=>({code,wins,losses,conference:'East'});
 const rows=referenceRows([t('C',0,0),t('B',2,4),t('A',1,2),t('D',4,1)],'East');
 assert.deepEqual(rows.map(r=>[r.code,r.rank]),[['D',1],['A',2],['B',2],['C',null]]);
 assert.equal(rows.at(-1).pct,null);
 assert.equal(referenceRows([t('A',-1,1),t('B',0.5,1)],'East').length,0);
});
test('design fixtures cover both conferences and every sample match has consistent derived results',()=>{
 assert.equal(TEAMS.length,30);assert.equal(new Set(TEAMS.map(t=>t.code)).size,30);
 for(const conference of ['East','West'])assert.equal(referenceRows(TEAMS,conference).length,15);
 for(const g of SETS.flat()){
  const m=resultMetrics(g);assert.ok(TEAMS.some(t=>t.code===m.winner));
  assert.equal(m.total,g.homeScore+g.awayScore);assert.equal(m.margin,Math.abs(g.homeScore-g.awayScore));
 }
 assert.equal(resultMetrics({homeScore:0,awayScore:0}),null);
 assert.equal(resultMetrics({homeScore:-1,awayScore:5}),null);
});

test('synthetic tracking stays on court, keeps a continuous loop and wraps its timeline',async()=>{
 const {TRACKS,sampleTrack}=await import('../../nba/court-motion.mjs');
 assert.equal(TRACKS.length,10);
 for(const track of TRACKS){
  assert.ok(track.length>0);
  for(const p of track.samples){assert.ok(p.x>=0&&p.x<=940);assert.ok(p.y>=0&&p.y<=500);}
  const a=sampleTrack(track,0),b=sampleTrack(track,1),nearEnd=sampleTrack(track,1-1e-8);
  assert.deepEqual(a,b);assert.ok(Math.hypot(a.x-nearEnd.x,a.y-nearEnd.y)<.001);
  assert.deepEqual(sampleTrack(track,.25),sampleTrack(track,2.25));
  assert.deepEqual(sampleTrack(track,-.25),sampleTrack(track,.75));
 }
});
