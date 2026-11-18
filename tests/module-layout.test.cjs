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
 vm.runInContext(read('inverters.js'),context);context.SolarCentral=C;
 let source=html.match(/<script>\s*'use strict';([\s\S]*)<\/script>\s*<\/body>/)[1];
 source=source.replace('syncSettings();startCentralApplication();','');
 vm.runInContext("'use strict';"+source,context);
 vm.runInContext(`centralBundle=inputs.bundle;state=WR.migratePlant(CENTRAL.toState(centralBundle.config));panelGeometry=state.panelGeometry;nearData=centralBundle.near;horizon=centralBundle.horizon.points;weather=inputs.weather;render=()=>{};calculate();`,context);
 return {ctx:context,nodes,run:s=>vm.runInContext(s,context)};
}
async function bundle(c=config,n=near,h=far){return C.verifyBundle(C.serialize(c),h,n)}
function weatherFixture(){const text=process.env.PV_TEST_WEATHER_FIXTURE?fs.readFileSync(process.env.PV_TEST_WEATHER_FIXTURE,'utf8'):execFileSync('git',['show','e94f948943a1d7593bcec1e7d777cec29b853763:prognosen/letzter_wetterstand.json'],{cwd:root,encoding:'utf8'});return JSON.parse(text).weather;}

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
module.exports={runtime,bundle};
