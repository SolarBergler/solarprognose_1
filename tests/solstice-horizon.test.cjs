'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
function between(start,end){
  const a=html.indexOf(start),b=html.indexOf(end,a+start.length);
  assert.ok(a>=0&&b>a, 'Cannot locate solar chart source: '+start);
  return html.slice(a,b);
}
const script=[
  between('function solarPosition(epoch){','function interpolateHorizon(az){'),
  between('function localDayStart(day){','// V7: Nur Anzeige und Abtasten.'),
  between('function renderHorizon(){','function dayAfter(s){'),
  between('function dayAfter(s){','function renderKwp(){')
].join('\n');

function draw(selectedDay='2026-11-20',latitude=47.697844){
  const els={
    horizonPlot:{innerHTML:''},
    horizonSvg:{getScreenCTM:()=>null,getBoundingClientRect:()=>({left:0,width:900})},
    horizonOverlay:{addEventListener:()=>{}},
    hoverInfo:{textContent:''}
  };
  const ctx={
    Math,Date,Intl,
    rad:Math.PI/180,deg:180/Math.PI,
    state:{lat:latitude,lon:11.880098},
    selectedDay,horizon:Array.from({length:720},(_,i)=>({az:i/2,height:12})),
    dayKey:ts=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(ts*1000)),
    clamp:(v,a,b)=>Math.max(a,Math.min(b,v)),
    interpolateHorizon:()=>12,
    number:(n)=>Number(n).toFixed(1),
    $:id=>els[id]
  };
  vm.createContext(ctx);
  vm.runInContext(script+'\nrenderHorizon()',ctx);
  return els.horizonPlot.innerHTML;
}

function reference(svg,season){
  const match=svg.match(new RegExp('<path class="sun-extreme-reference" data-season="'+season+'"[^>]+>'));
  assert.ok(match,season+' reference is missing');
  return match[0];
}
const coords=s=>[...s.matchAll(/(-?\d+\.\d) (-?\d+\.\d)/g)].map(m=>[Number(m[1]),Number(m[2])]);

test('annual summer/winter references have the same stroke as horizon, are solid and very thin',()=>{
  const svg=draw();
  const horizonStroke=svg.match(/id="horizonArea"[^>]*stroke="([^"]+)"/)?.[1];
  assert.equal(horizonStroke,'#a4d8a6');
  for(const season of ['summer','winter']){
    const tag=reference(svg,season);
    assert.ok(tag.includes('stroke="'+horizonStroke+'"'));
    assert.ok(tag.includes('stroke-width="1"'));
    assert.ok(tag.includes('fill="none"'));
    assert.ok(!tag.includes('stroke-dasharray'));
    assert.ok(coords(tag).length>25);
  }
  assert.equal((svg.match(/class="sun-extreme-reference"/g)||[]).length,2);
});

test('the June solstice is higher and fully inside the graph; the December solstice is lower',()=>{
  const svg=draw();
  const summer=coords(reference(svg,'summer')).map(p=>p[1]);
  const winter=coords(reference(svg,'winter')).map(p=>p[1]);
  const highestSummer=Math.min(...summer),highestWinter=Math.min(...winter);
  assert.ok(highestSummer>17, 'summer peak must not clip at the plot top');
  assert.ok(highestSummer<65, 'summer peak should approach plot top');
  assert.ok(highestWinter>highestSummer+60, 'winter reference must be visibly lower');
  assert.match(svg,/>70°<\/text>/, 'height axis needs room for summer elevation');
});

test('selected-day solar arc is still dashed gold and above annual references',()=>{
  const svg=draw('2026-11-20');
  const lastReference=svg.lastIndexOf('class="sun-extreme-reference"');
  const selected=svg.match(/<path d="M [^>]+stroke="#f3bf72"[^>]+>/);
  assert.ok(selected);
  assert.ok(selected[0].includes('stroke-dasharray="8 5"'));
  assert.ok(svg.indexOf(selected[0])>lastReference);
});

test('annual references also appear before a specific day is selected',()=>{
  const svg=draw(null);
  assert.ok(reference(svg,'summer'));
  assert.ok(reference(svg,'winter'));
  assert.ok(!svg.includes('stroke="#f3bf72"'));
});
