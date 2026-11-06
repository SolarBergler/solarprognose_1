const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const C=require('../central-config.js');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const initial={configText:read(C.FILE),horizonText:read('horizontprofil.json'),nearText:read('nahverschattung.json')};
const bundle=()=>C.verifyBundle(initial.configText,initial.horizonText,initial.nearText);
const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data,text:async()=>typeof data==='string'?data:JSON.stringify(data)});
function memory(){const data=new Map();return {getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),data};}
class GitHub {
  constructor(){this.files={[C.FILE]:initial.configText,'horizontprofil.json':initial.horizonText,'nahverschattung.json':initial.nearText};this.head='a'.repeat(40);this.calls=[];this.tree=[];this.race=false;this.lost=false;this.denied=false;this.blob=false;}
  fetch=async(url,options={})=>{
    this.calls.push({url,options});const p=new URL(url).pathname.replace('/repos/'+C.REPOSITORY,''),method=options.method||'GET';
    if(this.denied)return response({},403);
    if(p==='/git/ref/heads/main')return response({object:{sha:this.head}});
    if(p.startsWith('/contents/')){const name=p.slice(10);return this.blob?response({sha:'c'.repeat(40),encoding:'none'}):response({encoding:'base64',content:Buffer.from(this.files[name]).toString('base64')});}
    if(p.startsWith('/git/blobs/'))return response({encoding:'base64',content:Buffer.from(this.files[C.FILE]).toString('base64')});
    if(p.startsWith('/git/commits/')&&method==='GET')return response({tree:{sha:'b'.repeat(40)}});
    const body=JSON.parse(options.body||'{}');
    if(p==='/git/trees'){this.tree=body.tree;assert.equal(body.base_tree,'b'.repeat(40));return response({sha:'d'.repeat(40)});}
    if(p==='/git/commits'&&method==='POST'){this.parents=body.parents;return response({sha:'e'.repeat(40)});}
    if(p==='/git/refs/heads/main'){
      assert.equal(body.force,false);
      if(this.race)return response({},422);
      assert.deepEqual(this.parents,[this.head]);
      this.tree.forEach(f=>this.files[f.path]=f.content);this.head=body.sha;
      if(this.lost)throw Error('lost response');
      return response({object:{sha:this.head}});
    }
    throw Error('Unexpected request '+method+' '+p);
  };
}
const token='t'.repeat(40);
async function electrical(b){const s=C.toState(b.config);s.inverters[0].maxAcKw+=.5;return C.draftConfig(s,b.config);}

test('Zentrale physikalische und elektrische Werte bleiben beim Bearbeiten vollständig erhalten',async()=>{
  const b=await bundle(),far=JSON.parse(initial.horizonText);
  const copy=await C.draftConfig(C.toState(b.config),b.config);
  assert.deepEqual(copy.panels,b.config.panels);assert.deepEqual(copy.inverters,b.config.inverters);
  assert.equal(copy.systemLossesPercent,b.config.systemLossesPercent);assert.equal(copy.albedo,b.config.albedo);
  assert.equal(b.config.location.latitude,far.location.latitude);assert.equal(b.config.location.roofHeightM,far.location.roofHeight);
  assert.equal(b.configHash,await C.sha256(initial.configText));
});
test('Ein falsches oder teilweise veröffentlichtes Profil wird nie aktiviert',async()=>{
  await assert.rejects(()=>C.verifyBundle(initial.configText,initial.horizonText+' ',initial.nearText),e=>e.code==='PROFILE_MISMATCH');
  const c=JSON.parse(initial.configText);c.panels[0].geo.width_m+=1;c.profiles.geometryHash=await C.sha256(C.canonical(C.geometry(c)));
  await assert.rejects(()=>C.verifyBundle(C.serialize(c),initial.horizonText,initial.nearText),/Modulgeometrie/);
});
test('Cache enthält nur geprüfte zentrale Pakete; manipulierte Kopien werden abgelehnt',async()=>{
  const b=await bundle(),store=memory();C.cacheBundle(b,store);
  const offline=await C.loadBundle({store,fetchImpl:async()=>{throw Error('offline')}});
  assert.equal(offline.configHash,b.configHash);assert.equal(offline.online,false);
  const raw=JSON.parse(store.getItem(C.CACHE_KEY));raw.nearText+=' ';store.setItem(C.CACHE_KEY,JSON.stringify(raw));
  assert.equal(await C.readCache(store),null);
  await assert.rejects(()=>C.loadBundle({store,fetchImpl:async()=>{throw Error('offline')}}));
});
test('Lokale Einstellungsdateien werden vom zentralen Loader nicht gelesen',async()=>{
  const store=memory();store.setItem('schliersee-settings-v1',JSON.stringify({lat:0,losses:50}));
  const fetchImpl=async url=>response(url.includes(C.FILE)?initial.configText:url.includes('horizontprofil')?initial.horizonText:initial.nearText);
  const b=await C.loadBundle({store,fetchImpl});assert.equal(b.configHash,(await bundle()).configHash);
  assert.equal(JSON.parse(store.getItem('schliersee-settings-v1')).lat,0);
});
test('Elektrische Änderungen veröffentlichen nur die Konfiguration; Profilhashes bleiben unverändert',async()=>{
  const b=await bundle(),server=new GitHub();const candidate=await electrical(b);
  const result=await C.publish({token,expectedHash:b.configHash,candidate,fetchImpl:server.fetch});
  assert.equal(result.pagesReady,false);assert.equal(result.bundle.config.revision,b.config.revision+1);
  assert.deepEqual(server.tree.map(f=>f.path),[C.FILE]);
  assert.deepEqual(result.bundle.config.profiles,b.config.profiles);
  assert.notEqual(result.bundle.physicalHash,b.physicalHash);
  for(const call of server.calls){assert.ok(call.url.startsWith('https://api.github.com/repos/'+C.REPOSITORY+'/'));assert.equal(call.options.cache,'no-store');assert.equal(call.options.credentials,'omit');assert.equal(call.options.redirect,'error');}
  assert.ok(!JSON.stringify(result).includes(token));
});
test('Anzeigenamen ändern die Konfigurationsversion, aber nicht das physikalische Modell',async()=>{
  const b=await bundle(),s=C.toState(b.config);s.panels[0].name='Neuer Anzeigename';s.inverters[0].name='Umbenannt';
  const c=await C.draftConfig(s,b.config),updated=await C.verifyBundle(C.serialize(c),b.horizonText,b.nearText);
  assert.notEqual(updated.configHash,b.configHash);assert.equal(updated.physicalHash,b.physicalHash);
});
test('Veraltete Browserstände werden vor dem ersten Schreibzugriff zurückgewiesen',async()=>{
  const b=await bundle(),server=new GitHub();server.files[C.FILE]=C.serialize(await electrical(b));
  await assert.rejects(async()=>C.publish({token,expectedHash:b.configHash,candidate:await electrical(b),fetchImpl:server.fetch}),e=>e.code==='CONFLICT');
  assert.ok(server.calls.every(c=>c.options.method==='GET'));
});
test('Konkurrierender Main-Commit wird niemals mit force überschrieben',async()=>{
  const b=await bundle(),server=new GitHub();server.race=true;
  await assert.rejects(async()=>C.publish({token,expectedHash:b.configHash,candidate:await electrical(b),fetchImpl:server.fetch}),e=>e.code==='CONFLICT');
  assert.equal(server.files[C.FILE],initial.configText);
});
test('Geometrieänderung ohne zusammengehörige Profile ist gesperrt',async()=>{
  const b=await bundle(),server=new GitHub(),s=C.toState(b.config);s.panelGeometry[0].width_m+=1;
  const candidate=await C.draftConfig(s,b.config);
  await assert.rejects(async()=>C.publish({token,expectedHash:b.configHash,candidate,fetchImpl:server.fetch}),/beide neu berechneten Profile/);
  assert.ok(server.calls.every(c=>c.options.method==='GET'));
});
test('Schreibberechtigungen, unbekannte Parameter und beliebige Profil-URLs werden abgewiesen',async()=>{
  const b=await bundle(),server=new GitHub();server.denied=true;
  await assert.rejects(async()=>C.publish({token,expectedHash:b.configHash,candidate:await electrical(b),fetchImpl:server.fetch}),e=>e.code==='AUTH');
  const c=C.clone(b.config);c.accessToken='no-secret-allowed';assert.throws(()=>C.validateConfig(c),/Unbekannte/);
  delete c.accessToken;c.profiles.near.path='https://example.invalid/steal';assert.throws(()=>C.validateConfig(c),/Profilbindung/);
});
test('Verlorene Bestätigung nach erfolgreichem Git-Update wird anhand des zentralen Inhalts geprüft',async()=>{
  const b=await bundle(),server=new GitHub();server.lost=true;
  const result=await C.publish({token,expectedHash:b.configHash,candidate:await electrical(b),fetchImpl:server.fetch});
  assert.equal(result.commitSha,server.head);assert.equal(result.bundle.configHash,await C.sha256(server.files[C.FILE]));
});
