/* No browser emulation claim: execute the real calculation and archive functions
 * in Node's VM with passive DOM placeholders. Browser rendering is checked apart. */
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const C=require('../central-config.js'),root=path.join(__dirname,'..'),read=n=>fs.readFileSync(path.join(root,n),'utf8');
const config=JSON.parse(read('anlagenkonfiguration.json')),near=read('nahverschattung.json'),far=read('horizontprofil.json');
function runtime(bundle,html=read('index.html'),weather){
 const nodes=new Map(),store=new Map();
 const element=id=>{if(!nodes.has(id))nodes.set(id,{id,textContent:'',innerHTML:'',value:'',children:[],style:{},dataset:{},classList:{add(){},remove(){},toggle(){}},addEventListener(){},querySelectorAll(){return []},setAttribute(){},removeAttribute(){}});return nodes.get(id)};
 const context={console,crypto:globalThis.crypto,TextEncoder,AbortController,URL,Blob,Date,Map,Set,Intl,setTimeout,clearTimeout,setInterval:()=>0,
 document:{getElementById:element,addEventListener(){},querySelector(){return element('query')},hidden:false},
 localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,String(v)),removeItem:k=>store.delete(k)},addEventListener(){},
 inputs:{bundle,weather},nodes};context.window=context;context.globalThis=context;vm.createContext(context);
 for(const name of ['inverters.js','near-area.js','remaining-forecast.js'])vm.runInContext(read(name),context);context.SolarCentral=C;
 let source=html.match(/<script>\s*'use strict';([\s\S]*)<\/script>\s*<\/body>/)[1];
 source=source.replace('syncSettings();startCentralApplication();','');
 vm.runInContext("'use strict';"+source,context);
 vm.runInContext(`centralBundle=inputs.bundle;state=WR.migratePlant(CENTRAL.toState(centralBundle.config));panelGeometry=state.panelGeometry;nearData=centralBundle.near;horizon=centralBundle.horizon.points;weather=inputs.weather;render=()=>{};calculate();`,context);
 return {ctx:context,nodes,run:s=>vm.runInContext(s,context)};
}
async function bundle(c=config,n=near,h=far){return C.verifyBundle(C.serialize(c),h,n)}
function weatherFixture(){const text=process.env.PV_TEST_WEATHER_FIXTURE?fs.readFileSync(process.env.PV_TEST_WEATHER_FIXTURE,'utf8'):execFileSync('git',['show','e94f948943a1d7593bcec1e7d777cec29b853763:prognosen/letzter_wetterstand.json'],{cwd:root,encoding:'utf8'});return JSON.parse(text).weather;}

test('Schwachlichtkennlinie nutzt tatsächliche Einstrahlung und hält ältere Prognosen separat',async()=>{
 const oldConfig=C.clone(config);delete oldConfig.modulePowerModel;
 const oldBundle=await bundle(oldConfig),newBundle=await bundle();
 assert.notEqual(newBundle.physicalHash,oldBundle.physicalHash);
 assert.equal((await C.draftConfig(C.toState(config),config)).modulePowerModel,config.modulePowerModel);
 const invalid=C.clone(config);invalid.modulePowerModel='unknown';
 await assert.rejects(bundle(invalid),/Unbekanntes Modul-Leistungsmodell/);
 const r=runtime(oldBundle,undefined,weatherFixture());
 assert.equal(r.run('cSiRelativeEfficiency(1000,25)'),1);
 assert.equal(r.run('cSiRelativeEfficiency(25,25)'),r.run('cSiRelativeEfficiency(100,25)'));
 assert.ok(r.run('cSiRelativeEfficiency(100,25)')<r.run('cSiRelativeEfficiency(500,25)'));
 const at=Date.parse('2026-11-06T06:00:00+01:00'),day='2026-11-06';
 r.run(`saveForecastSnapshots(${at})`);
 const before=r.run(`JSON.stringify(forecastArchive.days['${day}'])`);
 r.ctx.newBundle=newBundle;
 r.run(`centralBundle=newBundle;calculate();saveForecastSnapshots(${at+3600000})`);
 assert.equal(r.run(`JSON.stringify(forecastArchive.previousModels['v12.8-${oldBundle.physicalHash}']['${day}'])`),before);
 assert.notDeepEqual(JSON.parse(r.run(`JSON.stringify(forecastArchive.days['${day}'].current)`)),JSON.parse(before).current);
 const night=r.run(`calculated.filter(row=>row.day==='${day}'&&row.sunlightMinutes===0)`);
 assert.ok(night.length>0&&night.every(row=>row.power===0));
});

test('Restprognose nutzt neue Zukunftswerte, während ursprüngliche Morgenkurve erhalten bleibt',async()=>{
 const r=runtime(await bundle(),undefined,weatherFixture());
 const morning=Date.parse('2026-11-06T06:00:00+01:00'),now=Date.parse('2026-11-06T12:02:30+01:00');
 r.run(`saveForecastSnapshots(${morning})`);
 const original=JSON.stringify(r.run('forecastArchive.days["2026-11-06"].original'));
 const first=r.run(`getRemainingForecast(${now})`);assert.equal(first.available,true);assert.ok(first.kWh>0);
 r.run(`for(const group of ['hourly','minutely_15'])for(const key of ['direct_normal_irradiance','shortwave_radiation','diffuse_radiation'])if(weather[group]?.[key])weather[group][key]=weather[group][key].map(v=>v===null?null:v*.5);calculate();saveForecastSnapshots(${now});renderRemainingForecast(${now});`);
 const after=r.run(`getRemainingForecast(${now})`);assert.ok(after.kWh<first.kWh*.55);assert.ok(after.kWh>first.kWh*.45);
 assert.equal(JSON.stringify(r.run('forecastArchive.days["2026-11-06"].original')),original);
 assert.ok(r.nodes.get('remainingEnergy').textContent.endsWith(' kWh'));
 r.run(`weatherIsCached=true;renderRemainingForecast(${now});`);
 assert.equal(r.nodes.get('remainingToday').dataset.stale,'true');assert.ok(r.nodes.get('remainingNote').textContent.includes('nicht live'));
});

test('Nachgeholter Stundenabruf beim Sichtbarwerden läuft einmal; Hintergrund und laufende Abrufe werden übersprungen',async()=>{
 const r=runtime(await bundle(),undefined,weatherFixture());
 r.ctx.Date=class extends Date{static now(){return Date.parse('2026-11-06T12:05:00+01:00')}};
 r.run(`weatherLastAttemptAt=Date.parse('2026-11-06T11:40:00+01:00');var refreshCalls=0;refreshCentralForecast=async()=>{refreshCalls++};document.hidden=true;`);
 assert.equal(await r.run('refreshForecastIfDue()'),false);assert.equal(r.run('refreshCalls'),0);
 r.run('document.hidden=false;working=true');assert.equal(await r.run('refreshForecastIfDue()'),false);
 r.run('working=false');assert.equal(await r.run('refreshForecastIfDue()'),true);
 assert.equal(await r.run('refreshForecastIfDue()'),false);assert.equal(r.run('refreshCalls'),1);
});

test('Bestätigte 88 Module, WR-Zuordnung, Wp-Gewichte und GPS-Anker bleiben konsistent',async()=>{
 const b=await bundle();assert.equal(b.config.panels.flatMap(p=>p.geo.modulePositions).length,88);
 assert.ok(Math.abs(b.config.panels.reduce((s,p)=>s+p.kwp,0)-31.305)<1e-9);
 const dc=Object.fromEntries(b.config.inverters.map(w=>[w.id,b.config.panels.filter(p=>p.inverterId===w.id).reduce((s,p)=>s+p.kwp,0)]));
 for(const [id,kwp] of Object.entries({'wr-1':6.275,'wr-2':7.18,'wr-3':9.9,'wr-4':7.95}))assert.ok(Math.abs(dc[id]-kwp)<1e-9);
 for(const p of b.config.panels){assert.equal(p.geo.modulePositions.length,p.moduleGroups.reduce((s,g)=>s+g.count,0));assert.ok(p.moduleGroups.every(g=>g.model&&g.dimensionsMm.length&&g.dimensionsMm.width));}
 const garage=b.config.panels.filter(p=>/^Garage (Ost|West)$/.test(p.name));assert.equal(garage.length,2);assert.deepEqual(garage.map(p=>[p.kwp,p.tilt,p.az]),[[.33,20,75],[.33,20,255]]);
 const changed=C.clone(b.near);changed.panelProfiles[0].sampleWeights[0]=450;
 assert.throws(()=>C.verifyPanelProfile(config.panels[0],changed.panelProfiles[0]),/Gewichte/);
 changed.panelProfiles[0].sampleWeights[0]=300;changed.panelProfiles[0].samplePositions[0].latitude+=.00001;
 assert.throws(()=>C.verifyPanelProfile(config.panels[0],changed.panelProfiles[0]),/Modulpositionen/);
 const draft=await C.draftConfig(C.toState(config),config);assert.deepEqual(draft.panels,config.panels);assert.deepEqual(draft.inverters,config.inverters);
});

test('300/450-Wp-Gewichtung ergibt bei genau einem freien Modul 60 Prozent, nicht 50 Prozent',async()=>{
 const c=C.clone(config);c.panels=[c.panels[0]];const p=c.panels[0];p.kwp=.75;c.albedo=0;
 for(const g of p.moduleGroups){delete g.commissionedOn;delete g.commissionedOnPrecision;delete g.annualDegradationPct;}
 p.geo.modulePositions=[p.geo.modulePositions[0],p.geo.modulePositions.at(-1)];
 const n=JSON.parse(near);n.panelProfiles=[n.panelProfiles[0]];const pr=n.panelProfiles[0];pr.samples=[Array(720).fill(89),Array(720).fill(0)];
 pr.sampleWeights=[300,450];pr.samplePositions=[pr.samplePositions[0],pr.samplePositions.at(-1)];
 n.config.panels=[C.clone(p)];const h=JSON.parse(far);h.points=h.points.map(p=>({...p,height:0}));
 const nt=JSON.stringify(n),ht=JSON.stringify(h);c.profiles.near.sha256=await C.sha256(nt);c.profiles.horizon.sha256=await C.sha256(ht);c.profiles.geometryHash=await C.sha256(C.canonical(C.geometry(c)));
 const w=weatherFixture();delete w.minutely_15;
 w.hourly.direct_normal_irradiance=w.hourly.time.map(()=>500);w.hourly.diffuse_radiation=w.hourly.time.map(()=>0);w.hourly.shortwave_radiation=w.hourly.time.map(()=>0);
 const r=runtime(await bundle(c,nt,ht),undefined,w);const rows=r.run('calculated.filter(r=>r.base>.001)');assert.ok(rows.length>100);
 for(const row of rows)assert.ok(Math.abs(row.power/row.base-.6)<1e-10,row.power/row.base);
});

test('Volle Fünfminutenkurven, Belegungsdarstellung und unveränderte Originalprognosen beim Fortschreiben',async()=>{
 const r=runtime(await bundle(),undefined,weatherFixture());
 const rows=r.run('calculated');assert.ok(rows.length>1900);const fullDay=rows.filter(r=>r.day==='2026-11-06');assert.equal(fullDay.length,288);for(let i=1;i<fullDay.length;i++)assert.equal(fullDay[i].ts-fullDay[i-1].ts,300);
 for(const row of rows){assert.ok(row.power>=0&&row.power<=27.00000001);assert.equal(row.byPanel.length,7);assert.ok(Math.abs(row.byPanel.reduce((s,p)=>s+p.power,0)-row.power)<1e-9);}
 r.run('renderPlantLayout()');assert.equal((r.nodes.get('plantLayout').innerHTML.match(/<polygon /g)||[]).length,88);
 r.run('panelsDraft=state.panels.map((p,i)=>({...p,geo:panelGeometry[i]}));invertersDraft=state.inverters;refreshPanelEditor();refreshInverterEditor();');
 assert.ok(r.nodes.get('panelsEdit').innerHTML.includes('JAM72S10-415/MR'));assert.ok(r.nodes.get('invertersEdit').innerHTML.includes('74050E87'));
 const a=Date.parse('2026-11-06T06:00:00+01:00');r.run(`saveForecastSnapshots(${a})`);
 const original=JSON.stringify(r.run('forecastArchive.days["2026-11-06"].original'));
 r.run(`for(const group of ['hourly','minutely_15'])for(const key of ['direct_normal_irradiance','shortwave_radiation','diffuse_radiation'])if(weather[group]?.[key])weather[group][key]=weather[group][key].map(v=>v===null?null:v*.5);calculate();saveForecastSnapshots(${a+3600000});`);
 assert.equal(JSON.stringify(r.run('forecastArchive.days["2026-11-06"].original')),original);
 const oldModel=r.run('archiveModelId()');r.run(`centralBundle={...centralBundle,physicalHash:'changed-layout-test'};saveForecastSnapshots(${a+7200000});`);
 assert.equal(JSON.stringify(r.run(`forecastArchive.previousModels[${JSON.stringify(oldModel)}]['2026-11-06'].original`)),original);
});
test('Garage Ost und West sind getrennt und DOM20-Nahprofile geometrisch zugeordnet',async()=>{
 const b=await bundle();
 const e=b.config.panels.find(p=>p.id==='panel-garage-east');
 const w=b.config.panels.find(p=>p.id==='panel-garage-west');
 assert.equal(e.az,75);assert.equal(w.az,255);
 assert.equal(e.geo.azimuth,75);assert.equal(w.geo.azimuth,255);
 assert.equal(e.geo.modulePositions[0].id,'2.1.16');assert.equal(w.geo.modulePositions[0].id,'2.1.15');
 assert.equal(e.tilt,20);assert.equal(w.tilt,20);
 assert.equal(e.kwp,.33);assert.equal(w.kwp,.33);
 assert.equal(e.inverterId,'wr-2');assert.equal(w.inverterId,'wr-2');
 const phi=e.geo.latitude*Math.PI/180;
 const deltaEast=(e.geo.longitude-w.geo.longitude)*Math.PI/180*
     (6378137/Math.sqrt(1-.00669437999014*Math.sin(phi)**2))*Math.cos(phi);
 const deltaNorth=(e.geo.latitude-w.geo.latitude)*Math.PI/180*(6378137*(1-.00669437999014)/Math.pow(1-.00669437999014*Math.sin(phi)**2,1.5));
 const centerDist=Math.hypot(deltaEast,deltaNorth),centerAz=Math.atan2(deltaEast,deltaNorth)*180/Math.PI;
 assert.ok(Math.abs(centerDist-(1.028*Math.cos(20*Math.PI/180)+.025))<.00001,'0,991 m Mittelpunkte');
 assert.ok(Math.abs(centerAz-75)<.005,'Abstand quer zum First');
 for(const p of [e,w]){assert.equal(p.geo.modulePositions[0].width_m,1.705);assert.equal(p.geo.modulePositions[0].depth_m,1.028);}

 for(const p of [e,w]){
   assert.equal(p.geo.modulePositions.length,1);
   const m=p.geo.modulePositions[0];
   assert.equal(m.latitude,p.geo.latitude);assert.equal(m.longitude,p.geo.longitude);
   const prof=b.near.panelProfiles[b.config.panels.indexOf(p)];
   assert.equal(prof.center.longitude,p.geo.longitude);
   assert.equal(prof.center.latitude,p.geo.latitude);
   assert.equal(prof.samplePositions[0].longitude,p.geo.longitude);
   assert.equal(prof.samplePositions[0].latitude,p.geo.latitude);
   assert.equal(prof.samples[0].length,720);
 }
 assert.notDeepEqual(b.near.panelProfiles.at(-2).samples,b.near.panelProfiles.at(-1).samples);
});

test('Modulbelegung: Hausfelder bündig, 25 mm Fuge, Nordpfeil, keine Modelldatenänderung',async()=>{
 const b=await bundle(),before=JSON.stringify(b.config);
 const r=runtime(b,undefined,weatherFixture());
 r.run('renderPlantLayout()');
 const drawing=r.nodes.get('plantLayout').innerHTML;
 assert.equal(JSON.stringify(b.config),before);
 assert.equal((drawing.match(/<polygon /g)||[]).length,88);
 assert.ok(drawing.includes('id="module-north-arrow"'));
 assert.ok(drawing.includes('>N</text>'));
 const polygons=[...drawing.matchAll(/<polygon points="([^"]+)"[^>]*><title>[^<]* · ([^ ]+) · [^<]*<\/title><\/polygon>/g)];
 assert.equal(polygons.length,88);
 const box=id=>{
   const entry=polygons.find(p=>p[2]===id);assert.ok(entry,'Modul fehlt: '+id);
   const pts=entry[1].split(' ').map(v=>v.split(',').map(Number));
   return {minX:Math.min(...pts.map(p=>p[0])),maxX:Math.max(...pts.map(p=>p[0])),minY:Math.min(...pts.map(p=>p[1]))};
 };
 const a=box('4.1.24'),bTop=box('1.1.1'),d=box('4.1.18'),e=box('1.1.13');
 assert.ok(Math.abs(bTop.minX-a.maxX-.025)<1e-8,'obere Fuge');
 assert.ok(Math.abs(bTop.minY-a.minY)<1e-8,'obere Reihe');
 assert.ok(Math.abs(e.minX-d.maxX-.025)<.005,'untere Fuge');
 assert.ok(Math.abs(e.minY-d.minY)<.005,'untere Reihe');
 const arrow=drawing.match(/id="module-north-arrow"[^>]*><title>Geografisch Nord<\/title><path d="M([\d.-]+) ([\d.-]+) L([\d.-]+) ([\d.-]+)"/);
 assert.ok(arrow,'Nordpfeil fehlt');
 const dx=+arrow[3]-arrow[1],dy=+arrow[4]-arrow[2];
 assert.ok(Math.abs(Math.atan2(dx,-dy)*180/Math.PI-15)<.0001,'Nordpfeilrichtung');
});

test('Fünf Hütte-vorne-Module bilden geometrisch eine lückenfreie Flucht mit 25 mm Fugen',async()=>{
 const b=await bundle(),original=JSON.stringify(b.config);
 const r=runtime(b,undefined,weatherFixture());
 r.run('renderPlantLayout()');
 const svg=r.nodes.get('plantLayout').innerHTML;
 assert.equal(JSON.stringify(b.config),original,'Modul-GPS-Daten dürfen sich nicht ändern');
 assert.equal((svg.match(/<polygon /g)||[]).length,88);
 assert.ok(svg.includes('id="module-north-arrow"'),'Kompass darf nicht verschwinden');
 const matches=[...svg.matchAll(/<polygon points="([^"]+)"[^>]*><title>Hütte vorne · (2\.1\.(?:17|18|19|20|21)) · 380 Wp<\/title><\/polygon>/g)];
 assert.equal(matches.length,5,'Alle fünf Hütteneinzelmodule müssen sichtbar sein');
 const polys=matches.sort((a,b)=>Number(a[2].split('.')[2])-Number(b[2].split('.')[2]))
     .map(match=>match[1].split(' ').map(coords=>coords.split(',').map(Number)));
 const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
 for(let i=0;i<4;i++){
   // Rendered order: next module follows the roofX direction from [1,2] to [0,3].
   const gapNear=distance(polys[i][1],polys[i+1][0]);
   const gapFar=distance(polys[i][2],polys[i+1][3]);
   assert.ok(Math.abs(gapNear-.025)<.003,'Keine Treppenkante: vorderer Rand zwischen '+(17+i)+' und '+(18+i)+' ('+gapNear+' m)');
   assert.ok(Math.abs(gapFar-.025)<.003,'Keine Treppenkante: hinterer Rand zwischen '+(17+i)+' und '+(18+i)+' ('+gapFar+' m)');
 }
 assert.equal(b.config.panels.find(p=>p.name==='Hütte vorne').az,255);
});

test('Alle Module in der Hausdach-Referenz 165° oder Vielfachen von 90°',async()=>{
 const bundleValue=await bundle();
 assert.equal(bundleValue.config.panels.find(p=>p.name==='Hütte vorne').az,255);
 assert.equal(bundleValue.config.panels.find(p=>p.name==='Haus links').az,165);
 for(const p of bundleValue.config.panels){
  assert.equal(((p.az-165)%90+90)%90,0,'Nicht parallele oder rechtwinklige Gruppe: '+p.name);
  assert.equal(p.geo.azimuth,p.az);
 }
 const hut=bundleValue.config.panels.find(p=>p.name==='Hütte vorne');
 const idx=bundleValue.config.panels.indexOf(hut),prof=bundleValue.near.panelProfiles[idx];
 for(let i=0;i<5;i++){
  assert.equal(hut.geo.modulePositions[i].latitude,prof.samplePositions[i].latitude);
  assert.equal(hut.geo.modulePositions[i].longitude,prof.samplePositions[i].longitude);
  assert.equal(prof.samples[i].length,720);
 }
});

test('Aktive Altersdegradation: sieben Jahrgänge und Monat/Jahr-Eingabe für bestehende und neue Felder',async()=>{
 const b=await bundle(),c=b.config,r=runtime(b,undefined,weatherFixture());
 const expected={'Haus links':['2016-10-01','2024-04-01'],'Garage':['2019-01-01','2019-01-01'],'Carport':['2020-07-01','2022-04-01'],'Hütte vorne':['2023-10-01'],'Haus rechts':['2016-10-01','2021-05-01'],'Garage Ost':['2019-01-01'],'Garage West':['2019-01-01']};
 let total=0,power=0;
 for(const panel of c.panels){
  assert.deepEqual(panel.moduleGroups.map(g=>g.commissionedOn),expected[panel.name]);
  for(const group of panel.moduleGroups){assert.equal(group.commissionedOnPrecision,'month');assert.equal(group.annualDegradationPct,1);}
  for(const module of panel.geo.modulePositions){assert.equal(module.wp,panel.moduleGroups[module.groupIndex].wp);power+=module.wp;total++;}
 }
 assert.equal(total,88);assert.equal(power,31305);
 const now=Date.parse('2026-11-18T00:00:00Z')/1000;
 const factors=r.run('moduleAgingFactors('+now+')');
 const agedPower=c.panels.reduce((s,p,i)=>s+p.geo.modulePositions.reduce((v,m,j)=>v+m.wp*factors[i].samples[j],0),0);
 assert.ok(agedPower>29000&&agedPower<29300,'Altersbereinigte DC-Leistung '+agedPower);
 const left=c.panels.findIndex(p=>p.name==='Haus links'),carport=c.panels.findIndex(p=>p.name==='Carport');
 const longiLeft=c.panels[left].geo.modulePositions.findIndex(m=>m.groupIndex===1);
 const longiCarport=c.panels[carport].geo.modulePositions.findIndex(m=>m.groupIndex===1);
 assert.ok(factors[left].samples[longiLeft]>factors[carport].samples[longiCarport]);
 const previous=C.clone(c);
 for(const p of previous.panels)for(const g of p.moduleGroups){delete g.commissionedOn;delete g.commissionedOnPrecision;delete g.annualDegradationPct;}
 const unaged=await bundle(previous);assert.notEqual(b.physicalHash,unaged.physicalHash);
 const oldRows=runtime(unaged,undefined,weatherFixture()).run('calculated'),newRows=r.run('calculated');
 assert.equal(oldRows.length,newRows.length);
 for(let i=0;i<newRows.length;i++)assert.ok(newRows[i].power<=oldRows[i].power+1e-8);
 r.run('panelsDraft=state.panels.map((p,i)=>({...p,moduleGroups:JSON.parse(JSON.stringify(p.moduleGroups)),geo:panelGeometry[i]}));refreshPanelEditor()');
 let editor=r.nodes.get('panelsEdit').innerHTML;
 assert.ok(editor.includes('type="month"'));
 assert.ok(editor.includes('value="2016-10"'));
 assert.ok(editor.includes('value="2024-04"'));
 assert.ok(editor.includes('value="2022-04"'));
 assert.equal(r.run("monthToCommissionedOn('2024-04')"),'2024-04-01');
 assert.equal(r.run("monthToCommissionedOn('2024-14')"),null);
 const newField={id:'test-new-field',name:'Test',kwp:1,az:165,tilt:20,inverterId:null,geo:{latitude:0,longitude:0,width_m:1,depth_m:1,lower_edge_height_m:1,upper_edge_height_m:2},commissionedOn:'2025-03-01',commissionedOnPrecision:'month',annualDegradationPct:1};
 const newConfig=C.clone(c);newConfig.panels.push(newField);
 assert.equal(C.validateConfig(newConfig),newConfig);
 const noDate=C.clone(newConfig);noDate.panels.at(-1).commissionedOn='2025-02-30';
 assert.throws(()=>C.validateConfig(noDate),/Inbetriebnahmemonat/);
 const draft=await C.draftConfig(C.toState(newConfig),newConfig);
 assert.equal(draft.panels.at(-1).commissionedOn,'2025-03-01');
});

module.exports={runtime,bundle};
