// A choreographed motion study, never actual player tracking or a paid data feed.
const FORMATIONS = [
 [[310,250],[230,90],[230,410],[155,165],[150,335],[380,250],[300,110],[300,390],[235,185],[230,315]],
 [[470,220],[410,80],[420,420],[520,160],[530,340],[535,235],[475,110],[480,390],[595,180],[600,320]],
 [[665,245],[690,80],[680,420],[800,150],[815,335],[735,255],[750,110],[745,390],[845,180],[855,305]],
 [[735,185],[645,345],[825,405],[745,95],[790,260],[785,205],[715,325],[855,375],[800,125],[850,250]],
 [[480,270],[430,110],[410,400],[355,175],[340,330],[540,260],[495,135],[480,370],[420,190],[405,315]],
 [[235,265],[120,100],[150,410],[220,170],[110,325],[300,250],[195,130],[220,375],[285,185],[190,305]],
];
const STEPS=60,NS='http://www.w3.org/2000/svg',DURATION=28000;
const point=(points,segment,t)=>{
 const n=points.length,p0=points[(segment+n-1)%n],p1=points[segment%n],p2=points[(segment+1)%n],p3=points[(segment+2)%n];
 // Closed Catmull-Rom interpolation keeps the end of the study continuous.
 return [0,1].map(a=>.5*((2*p1[a])+(-p0[a]+p2[a])*t+(2*p0[a]-5*p1[a]+4*p2[a]-p3[a])*t*t+(-p0[a]+3*p1[a]-3*p2[a]+p3[a])*t*t*t));
};
export function buildTrack(points){
 const samples=[];let length=0;
 for(let i=0;i<=points.length*STEPS;i++){
  const [x,y]=point(points,Math.min(Math.floor(i/STEPS),points.length-1),i===points.length*STEPS?1:(i%STEPS)/STEPS);
  const previous=samples.at(-1);if(previous)length+=Math.hypot(x-previous.x,y-previous.y);
  samples.push({x,y,length});
 }
 return {samples,length};
}
export function sampleTrack(track,phase){
 const p=((phase%1)+1)%1*(track.samples.length-1),i=Math.floor(p),t=p-i,a=track.samples[i],b=track.samples[i+1];
 return {x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t,progress:(a.length+(b.length-a.length)*t)/track.length};
}
export const TRACKS=Object.freeze(Array.from({length:10},(_,i)=>buildTrack(FORMATIONS.map(f=>f[i]))));
export function initCourtMotion(svg,control,reduced){
 const create=(tag,attrs)=>{const n=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,String(v));return n;};
 const root=create('g',{'class':'court-motion',id:'court-motion'});control.setAttribute('aria-controls','court-motion');root.setAttribute('aria-hidden','true');
 const scan=create('g',{'class':'court-scan'});
 scan.append(create('rect',{x:-8,y:1,width:16,height:498,'class':'scan-band'}),create('path',{d:'M0 1V499M-9 1H9M-9 499H9','class':'scan-line'}));root.append(scan);
 const nodes=TRACKS.map((track,i)=>{
  const g=create('g',{'class':`motion-track ${i<5?'attack':'defence'}`,'data-track':i+1});
  const pulse=create('g',{'class':'track-pulse',opacity:0});
  pulse.append(create('path',{d:'M-22 -10V-22H-10M10 -22H22V-10M22 10V22H10M-10 22H-22V10','class':'pulse-frame'}));g.append(pulse);
  const marker=create('g',{'class':'track-marker'});
  marker.append(create('path',{d:'M-13 0H-7M7 0H13M0-13V-7M0 7V13','class':'signal-cross'}),create('path',{d:'M0-4L4 0L0 4L-4 0Z','class':'signal-core'}));
  g.append(marker);root.append(g);return {g,marker,track,pulse,stamp:null,sweep:-1};
 });
 svg.append(root);
 let phase=.23,paused=false,visible=true,raf=null,last=0,clock=0;
 function draw(){
  // One quiet acquisition sweep every nine seconds, followed by a rest.
  const scanTime=clock+1800,sweep=Math.floor(scanTime/9000),scanPhase=(scanTime%9000)/7500,scanX=Math.min(1,scanPhase)*940;
  scan.setAttribute('transform',`translate(${scanX.toFixed(2)} 0)`);scan.setAttribute('opacity',reduced.matches||scanPhase>=1?0:.65);
  for(const n of nodes){
   const p=sampleTrack(n.track,phase);n.marker.setAttribute('transform',`translate(${p.x.toFixed(2)} ${p.y.toFixed(2)})`);
   if(!reduced.matches&&scanPhase<1&&Math.abs(scanX-p.x)<16&&n.sweep!==sweep){n.stamp={x:p.x,y:p.y,time:clock};n.sweep=sweep;}
   // The expanding reception stays at the acquired location, never trails the player.
   const age=n.stamp?(clock-n.stamp.time)/1600:1,intensity=Math.max(0,1-age);
   n.marker.setAttribute('opacity',(.52+.48*intensity).toFixed(3));
   if(n.stamp){n.pulse.setAttribute('transform',`translate(${n.stamp.x.toFixed(2)} ${n.stamp.y.toFixed(2)}) scale(${(1+Math.min(1,age)*1.8).toFixed(3)})`);}
   n.pulse.setAttribute('opacity',reduced.matches?0:(.78*intensity*intensity).toFixed(3));
  }
 }
 const running=()=>visible&&!paused&&!reduced.matches;
 function tick(time){
  raf=null;if(!running())return;
  if(!last)last=time;
  if(time-last>=1000/30){const elapsed=Math.min(time-last,100);clock+=elapsed;phase=(phase+elapsed/DURATION)%1;last=time;draw();}
  raf=requestAnimationFrame(tick);
 }
 function sync(){
  root.dataset.motion=reduced.matches?'static':paused?'paused':visible?'running':'idle';
  control.hidden=reduced.matches;control.textContent=paused?'動きを再開':'動きを止める';control.setAttribute('aria-label',paused?'コートのシグナルの動きを再開':'コートのシグナルの動きを止める');
  if(running()){if(raf===null){last=0;raf=requestAnimationFrame(tick);}}
  else{if(raf!==null)cancelAnimationFrame(raf);raf=null;last=0;}
 }
 control.addEventListener('click',()=>{paused=!paused;sync();});
 reduced.addEventListener('change',()=>{if(reduced.matches){phase=.23;nodes.forEach(n=>{n.stamp=null;});draw();}sync();});
 draw();sync();
 return {setVisible(value){visible=value;sync();}};
}
