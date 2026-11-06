/* V12.8.2: Eine veröffentlichte Konfiguration mit kryptographisch gebundenen Profilen. */
(function(root){
  'use strict';
  const FILE='anlagenkonfiguration.json',CACHE_KEY='solar-central-bundle-v1';
  const REPOSITORY='SolarBergler/solarprognose_1',API='https://api.github.com/repos/'+REPOSITORY;
  const GEO=['latitude','longitude','width_m','depth_m','lower_edge_height_m','upper_edge_height_m'];
  const clone=value=>JSON.parse(JSON.stringify(value));
  const serialize=value=>JSON.stringify(value,null,2)+'\n';
  const canonical=value=>value===null||typeof value!=='object'?JSON.stringify(value):Array.isArray(value)?
    '['+value.map(canonical).join(',')+']':'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  const fail=(message,code='INVALID')=>Object.assign(new Error(message),{code});
  async function sha256(text){
    const digest=await root.crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
    return [...new Uint8Array(digest)].map(v=>v.toString(16).padStart(2,'0')).join('');
  }
  const finite=(n,min,max)=>typeof n==='number'&&Number.isFinite(n)&&n>=min&&n<=max;
  function geometry(config){
    return {latitude:config.location.latitude,longitude:config.location.longitude,roofHeightM:config.location.roofHeightM,
      panels:config.panels.map(p=>({id:p.id,az:p.az,tilt:p.tilt,geo:Object.fromEntries(GEO.map(k=>[k,p.geo[k]]))}))};
  }
  function validateConfig(c){
    const allowed=['schemaVersion','revision','updatedAt','location','systemLossesPercent','albedo','panels','inverters','profiles'];
    if(!c||Object.keys(c).some(k=>!allowed.includes(k)))throw fail('Unbekannte Felder in der zentralen Konfiguration.');
    if(c?.schemaVersion!==1||!Number.isInteger(c.revision)||c.revision<1||!Number.isFinite(Date.parse(c.updatedAt)))throw fail('Ungültige zentrale Konfigurationsversion.');
    const l=c.location;
    if(!l||typeof l.name!=='string'||!l.name.trim()||l.name.length>50||!finite(l.latitude,-90,90)||!finite(l.longitude,-180,180)||!finite(l.roofHeightM,0,100)||
       !finite(c.systemLossesPercent,0,50)||!finite(c.albedo,0,1))throw fail('Standort oder Berechnungsparameter sind ungültig.');
    if(!Array.isArray(c.panels)||!c.panels.length||c.panels.length>24||!Array.isArray(c.inverters)||c.inverters.length>32)throw fail('Ungültige Anzahl von Modulfeldern oder Wechselrichtern.');
    const unique=list=>list.every(x=>typeof x.id==='string'&&x.id&&x.id.length<=100)&&new Set(list.map(x=>x.id)).size===list.length;
    if(!unique(c.panels)||!unique(c.inverters))throw fail('Interne IDs müssen eindeutig sein.');
    if(c.inverters.some(w=>typeof w.name!=='string'||!w.name.trim()||w.name.length>50||(w.maxAcKw!==null&&!finite(w.maxAcKw,.000001,1000000))))throw fail('Ungültige Wechselrichterleistung; AC-Wirkleistung in kW verwenden.');
    const ids=new Set(c.inverters.map(w=>w.id));
    for(const p of c.panels){
      if(typeof p.name!=='string'||!p.name.trim()||p.name.length>50||!finite(p.kwp,.000001,1000000)||!finite(p.az,0,360)||!finite(p.tilt,0,90)||
         !(p.inverterId===null||ids.has(p.inverterId)))throw fail('Ungültiges Modulfeld oder unbekannte WR-Zuordnung.');
      const g=p.geo;
      if(!g||!finite(g.latitude,-90,90)||!finite(g.longitude,-180,180)||!finite(g.width_m,.000001,100000)||!finite(g.depth_m,.000001,100000)||
         !finite(g.lower_edge_height_m,-1000,10000)||!finite(g.upper_edge_height_m,-1000,10000))throw fail('Modulgeometrie ist unvollständig.');
    }
    const profiles=c.profiles;
    if(profiles?.horizon?.path!=='horizontprofil.json'||profiles?.near?.path!=='nahverschattung.json'||!profiles.near.id||
       ![profiles.horizon.sha256,profiles.near.sha256,profiles.geometryHash].every(h=>typeof h==='string'&&/^[a-f0-9]{64}$/.test(h)))throw fail('Profilbindung fehlt oder ist ungültig.');
    return c;
  }
  async function verifyBundle(configText,horizonText,nearText){
    let c,h,n;
    try{c=JSON.parse(configText);h=JSON.parse(horizonText);n=JSON.parse(nearText);}catch{throw fail('Zentrale Konfiguration oder Profile enthalten kein gültiges JSON.');}
    validateConfig(c);
    if(await sha256(horizonText)!==c.profiles.horizon.sha256||await sha256(nearText)!==c.profiles.near.sha256||
       await sha256(canonical(geometry(c)))!==c.profiles.geometryHash)throw fail('Konfiguration und Profile gehören noch nicht zur selben Veröffentlichung.','PROFILE_MISMATCH');
    const l=c.location;
    if(!h.location||Math.abs(h.location.latitude-l.latitude)>0.00001||Math.abs(h.location.longitude-l.longitude)>0.00001||Math.abs(h.location.roofHeight-l.roofHeightM)>.05||
       !Array.isArray(h.points)||h.points.length!==720||h.points.some((p,i)=>!finite(p.az,0,359.999999)||!finite(p.height,0,89)||(i>0&&p.az<=h.points[i-1].az)))throw fail('Das zentrale Berghorizontprofil ist ungültig.');
    if(n.version!==1||n.kind!=='dom20-nearshade'||!/DOM20/i.test(n.source||'')||n.id!==c.profiles.near.id||!n.location||
       Math.abs(n.location.latitude-l.latitude)>.00001||Math.abs(n.location.longitude-l.longitude)>.00001||!Array.isArray(n.panelProfiles)||n.panelProfiles.length!==c.panels.length||
       !Array.isArray(n.config?.panels)||n.config.panels.length!==c.panels.length)throw fail('DOM20-Profil gehört nicht zur zentralen Anlage.');
    c.panels.forEach((p,i)=>{
      const profile=n.panelProfiles[i],meta=n.config.panels[i];
      if(!profile?.center||Math.abs(profile.center.latitude-p.geo.latitude)>.000001||Math.abs(profile.center.longitude-p.geo.longitude)>.000001||
         meta.az!==p.az||meta.tilt!==p.tilt||GEO.some(k=>Number(meta.geo?.[k])!==p.geo[k])||
         !Array.isArray(profile.samples)||profile.samples.length!==9||profile.samples.some(a=>!Array.isArray(a)||a.length!==720||a.some(v=>!finite(v,0,89.999999))))throw fail('DOM20-Profil und Modulgeometrie stimmen nicht überein: '+p.name);
    });
    // Anzeigenamen und Veröffentlichungszeit ändern das physikalische Modell nicht.
    const physical={geometry:geometry(c),losses:c.systemLossesPercent,albedo:c.albedo,profiles:[c.profiles.horizon.sha256,c.profiles.near.sha256],
      panels:c.panels.map(p=>[p.id,p.kwp,p.inverterId]),inverters:c.inverters.map(w=>[w.id,w.maxAcKw]).sort((a,b)=>a[0].localeCompare(b[0]))};
    return {config:c,horizon:h,near:n,configText,horizonText,nearText,configHash:await sha256(configText),physicalHash:await sha256(canonical(physical)),online:true};
  }
  function storage(){try{return root.localStorage}catch{return null}}
  async function readCache(store=storage()){
    try{
      const raw=JSON.parse(store?.getItem(CACHE_KEY)||'null');
      if(!raw)return null;
      const b=await verifyBundle(raw.configText,raw.horizonText,raw.nearText);
      if(b.configHash!==raw.configHash||b.physicalHash!==raw.physicalHash)return null;
      return {...b,online:false,cachedAt:raw.fetchedAt};
    }catch{return null}
  }
  function cacheBundle(bundle,store=storage()){
    try{store?.setItem(CACHE_KEY,JSON.stringify({configText:bundle.configText,horizonText:bundle.horizonText,nearText:bundle.nearText,configHash:bundle.configHash,physicalHash:bundle.physicalHash,fetchedAt:new Date().toISOString()}));}catch{/* Prognose bleibt bei gesperrtem Cache nutzbar. */}
  }
  async function loadBundle({fetchImpl=root.fetch?.bind(root),store=storage(),known=null,allowCache=true,retries=2,retryDelayMs=1000,onProgress=()=>{}}={}){
    let lastError;
    for(let attempt=0;attempt<=retries;attempt++){
      const controllers=[];
      try{
        const get=async path=>{
          onProgress('Lade '+path+' · Versuch '+(attempt+1)+'/'+(retries+1)+' …');
          const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);controllers.push(controller);
          try{
            const r=await fetchImpl('./'+path+'?central='+Date.now()+'-'+attempt,{cache:'no-store',signal:controller.signal});
            if(!r.ok)throw fail(path+': HTTP '+r.status+'.','NETWORK');
            return await r.text();
          }catch(error){throw error.code==='NETWORK'?error:fail(path+': '+(controller.signal.aborted?'Download nach 15 Sekunden abgebrochen.':'Download fehlgeschlagen; bitte Internetverbindung oder Browser-Blockierung prüfen.'),'NETWORK');}
          finally{clearTimeout(timer);}
        };
        const configText=await get(FILE),hash=await sha256(configText);
        if(known?.configHash===hash){const fresh={...known,online:true};cacheBundle(fresh,store);return fresh;}
        const [h,n]=await Promise.all([get('horizontprofil.json'),get('nahverschattung.json')]);
        onProgress('Prüfe Konfiguration und beide Verschattungsprofile …');
        const bundle=await verifyBundle(configText,h,n);cacheBundle(bundle,store);return bundle;
      }catch(error){
        lastError=error.code?error:fail('Konfiguration konnte nicht geprüft werden: '+error.message,'INVALID');
        if(allowCache){const cached=await readCache(store);if(cached)return {...cached,warning:lastError.code==='PROFILE_MISMATCH'?'Eine neue Veröffentlichung ist noch nicht vollständig verfügbar.':lastError.message};}
        if(attempt===retries||!['NETWORK','PROFILE_MISMATCH'].includes(lastError.code))throw lastError;
      }finally{controllers.forEach(c=>c.abort());}
      onProgress(lastError.message+' Automatischer neuer Versuch …');
      await new Promise(resolve=>setTimeout(resolve,retryDelayMs));
    }
  }
  function toState(c){
    return {locationName:c.location.name,lat:c.location.latitude,lon:c.location.longitude,roofHeight:c.location.roofHeightM,losses:c.systemLossesPercent,albedo:c.albedo,
      panels:c.panels.map(({geo,...p})=>clone(p)),inverters:clone(c.inverters),panelGeometry:c.panels.map(p=>clone(p.geo))};
  }
  async function draftConfig(state,base,{horizonText,nearText}={}){
    const c=clone(base);
    c.revision=base.revision+1;c.updatedAt=new Date().toISOString();
    c.location={name:state.locationName,latitude:state.lat,longitude:state.lon,roofHeightM:state.roofHeight};
    c.systemLossesPercent=state.losses;c.albedo=state.albedo;
    c.panels=state.panels.map((p,i)=>({id:p.id,name:p.name,kwp:p.kwp,az:p.az,tilt:p.tilt,inverterId:p.inverterId||null,geo:clone(state.panelGeometry[i])}));
    c.inverters=state.inverters.map(w=>({id:w.id,name:w.name,maxAcKw:w.maxAcKw}));
    c.profiles.geometryHash=await sha256(canonical(geometry(c)));
    if(horizonText)c.profiles.horizon.sha256=await sha256(horizonText);
    if(nearText){c.profiles.near.sha256=await sha256(nearText);c.profiles.near.id=JSON.parse(nearText).id;}
    validateConfig(c);return c;
  }
  function decode(text){return new TextDecoder().decode(Uint8Array.from(root.atob(text.replace(/\s/g,'')),c=>c.charCodeAt(0)));}
  async function publish({token,expectedHash,candidate,horizonText,nearText,fetchImpl=root.fetch?.bind(root)}){
    if(typeof token!=='string'||!token.trim()||!/^\S{20,}$/.test(token))throw fail('Bitte einen gültigen, auf dieses Repository beschränkten GitHub-Zugriffsschlüssel eingeben.','AUTH');
    if(!/^[a-f0-9]{64}$/.test(expectedHash))throw fail('Die Ausgangsversion fehlt. Bitte die zentrale Konfiguration neu laden.','CONFLICT');
    const request=async(path,method='GET',body)=>{
      let r,data;const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
      try{r=await fetchImpl(API+path,{method,cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer',redirect:'error',signal:controller.signal,headers:{Accept:'application/vnd.github+json',Authorization:'Bearer '+token,'X-GitHub-Api-Version':'2022-11-28',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});if(r.ok)data=await r.json();}
      catch{throw fail('GitHub ist nicht erreichbar. Der Speicherstatus muss vor einem erneuten Versuch geprüft werden.','NETWORK');}
      finally{clearTimeout(timer);}
      if(!r.ok){if([409,422].includes(r.status))throw fail('GitHub wurde zwischenzeitlich geändert. Bitte den neuen zentralen Stand laden; dein Entwurf wurde nicht darübergeschrieben.','CONFLICT');
        throw fail(r.status===401?'GitHub hat den Zugriffsschlüssel abgelehnt.':r.status===403?'GitHub erlaubt mit diesem Schlüssel keinen Schreibzugriff auf das Repository.':'GitHub-Anfrage fehlgeschlagen (HTTP '+r.status+').',r.status===401||r.status===403?'AUTH':'GITHUB');}
      return data;
    };
    const file=async(path,ref)=>{
      let doc=await request('/contents/'+path+'?ref='+encodeURIComponent(ref));
      if(doc.encoding!=='base64')doc=await request('/git/blobs/'+doc.sha);
      if(doc.encoding!=='base64'||typeof doc.content!=='string')throw fail('GitHub-Datei konnte nicht gelesen werden.');
      return decode(doc.content);
    };
    try{
      const ref=await request('/git/ref/heads/main'),baseSha=ref.object.sha;
      const currentText=await file(FILE,baseSha);
      if(await sha256(currentText)!==expectedHash)throw fail('Ein anderes Gerät hat die zentrale Konfiguration geändert. Bitte den neuen Stand laden. Dein Entwurf wurde nicht veröffentlicht.','CONFLICT');
      const current=validateConfig(JSON.parse(currentText));
      const c=clone(candidate);c.revision=current.revision+1;c.updatedAt=new Date().toISOString();validateConfig(c);
      if(c.profiles.geometryHash!==current.profiles.geometryHash&&(!horizonText||!nearText))throw fail('Geometrische Änderungen benötigen beide neu berechneten Profile.');
      const [h,n,base]=await Promise.all([horizonText||file('horizontprofil.json',baseSha),nearText||file('nahverschattung.json',baseSha),request('/git/commits/'+baseSha)]);
      const configText=serialize(c),bundle=await verifyBundle(configText,h,n);
      const tree=[{path:FILE,mode:'100644',type:'blob',content:configText}];
      if(horizonText)tree.push({path:'horizontprofil.json',mode:'100644',type:'blob',content:horizonText});
      if(nearText)tree.push({path:'nahverschattung.json',mode:'100644',type:'blob',content:nearText});
      const created=await request('/git/trees','POST',{base_tree:base.tree.sha,tree});
      const commit=await request('/git/commits','POST',{message:'Anlagenkonfiguration zentral veröffentlicht · Version '+c.revision,tree:created.sha,parents:[baseSha]});
      try{
        // Der Commit basiert auf baseSha. Ein zwischenzeitlicher fremder Commit macht dies zu einem
        // abgelehnten Non-Fast-Forward; force wird niemals benutzt, auch nicht bei Wetterdaten-Commits.
        await request('/git/refs/heads/main','PATCH',{sha:commit.sha,force:false});
      }catch(error){
        if(error.code==='NETWORK'){
          try{if(await sha256(await file(FILE,'main'))===bundle.configHash)return {bundle,commitSha:commit.sha,pagesReady:false};}catch{/* Ergebnis bleibt ausdrücklich unklar. */}
          throw fail('Die Verbindung brach beim Speichern ab. Der GitHub-Speicherstatus ist unklar. Bitte vor einem neuen Versuch den zentralen Stand neu laden.','UNCERTAIN');
        }
        throw error;
      }
      return {bundle,commitSha:commit.sha,pagesReady:false};
    }finally{token='';}
  }
  const api={FILE,CACHE_KEY,REPOSITORY,canonical,serialize,sha256,geometry,validateConfig,verifyBundle,readCache,cacheBundle,loadBundle,toState,draftConfig,publish,clone};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.SolarCentral=Object.freeze(api);
})(typeof globalThis!=='undefined'?globalThis:this);
