/* V12.7: AC-Wirkleistungsgrenzen. Keine zusätzliche Wirkungsgradannahme. */
(function(root){
  'use strict';
  const MAX_INVERTERS=32, MODEL='v12.7-ac-limit-1';
  function createId(){
    return 'wr-'+(root.crypto?.randomUUID?.() || Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
  }
  function migratePlant(settings){
    const seen=new Set();
    const source=Array.isArray(settings.inverters)?settings.inverters:
      Array.from({length:4},(_,i)=>({id:'wr-'+(i+1),name:'WR'+(i+1),maxAcKw:null}));
    const inverters=source.map(w=>{
      let id=typeof w.id==='string'&&w.id?w.id:createId();
      if(seen.has(id))id=createId();
      seen.add(id);
      return {...w,id,name:String(w.name||''),maxAcKw:w.maxAcKw==null||w.maxAcKw===''?null:Number(w.maxAcKw)};
    });
    const panels=settings.panels.map((p,i)=>({...p,id:p.id||'panel-'+(i+1),inverterId:p.inverterId||null}));
    return {...settings,inverters,panels};
  }
  function configurationStatus(panels,inverters){
    const ids=new Set(inverters.map(w=>w.id));
    const missingFields=panels.filter(p=>!p.inverterId||!ids.has(p.inverterId)).map(p=>p.name);
    const used=new Set(panels.map(p=>p.inverterId).filter(Boolean));
    const missingLimits=inverters.filter(w=>used.has(w.id)&&!(Number.isFinite(w.maxAcKw)&&w.maxAcKw>0)).map(w=>w.name);
    const configured=panels.length>0&&inverters.length<=MAX_INVERTERS&&ids.size===inverters.length&&
      inverters.every(w=>typeof w.id==='string'&&w.id&&w.name.trim())&&!missingFields.length&&!missingLimits.length;
    return {configured,missingFields,missingLimits,status:configured?'AC-Begrenzung aktiv':'Noch nicht konfiguriert'};
  }
  function compileLimits(panels,inverters){
    const status=configurationStatus(panels,inverters);
    return {...status,groups:status.configured?inverters.map(w=>({id:w.id,limit:w.maxAcKw,
      indices:panels.map((p,i)=>p.inverterId===w.id?i:-1).filter(i=>i>=0)})).filter(g=>g.indices.length):[]};
  }
  function limitPower(values,plan){
    if(values.some(v=>!Number.isFinite(v)||v<0))throw Error('Ungültige Modulfeldleistung.');
    const power=values.slice(),clipping=values.map(()=>0),byInverter=[];
    if(plan.configured)for(const group of plan.groups){
      const before=group.indices.reduce((s,i)=>s+values[i],0),after=Math.min(before,group.limit);
      const factor=before>0?after/before:1;
      for(const i of group.indices){power[i]=values[i]*factor;clipping[i]=Math.max(0,values[i]-power[i]);}
      byInverter.push({id:group.id,power:after,clipping:before-after});
    }
    return {power,clipping,byInverter,total:power.reduce((s,v)=>s+v,0),loss:clipping.reduce((s,v)=>s+v,0)};
  }
  function inverterSummary(w,panels){
    const assigned=panels.filter(p=>p.inverterId===w.id),dcKwp=assigned.reduce((s,p)=>s+(Number(p.kwp)||0),0);
    return {assigned,dcKwp,ratio:Number.isFinite(w.maxAcKw)&&w.maxAcKw>0?dcKwp/w.maxAcKw:null};
  }
  function removeInverter(inverters,panels,id){
    if(panels.some(p=>p.inverterId===id))throw Error('Bitte zuerst alle zugeordneten Modulfelder einem anderen Wechselrichter zuordnen.');
    return inverters.filter(w=>w.id!==id);
  }
  function modelConfiguration(panels,inverters){
    // Anzeigenamen ändern weder Physik noch Modellkennung.
    return [MODEL,inverters.map(w=>[w.id,w.maxAcKw]).sort((a,b)=>a[0].localeCompare(b[0])),panels.map(p=>p.inverterId||null)];
  }
  function configurationSnapshot(panels,inverters){
    return {schema:1,model:MODEL,...configurationStatus(panels,inverters),
      inverters:inverters.map(w=>{const s=inverterSummary(w,panels);return {...w,connectedDcKwp:s.dcKwp,dcAcRatio:s.ratio,assignedPanelIds:s.assigned.map(p=>p.id)};}),
      panels:panels.map(p=>({id:p.id,name:p.name,dcKwp:p.kwp,inverterId:p.inverterId}))};
  }
  const api={MAX_INVERTERS,MODEL,createId,migratePlant,configurationStatus,compileLimits,limitPower,
    inverterSummary,removeInverter,modelConfiguration,configurationSnapshot};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.SolarInverters=Object.freeze(api);
})(typeof globalThis!=='undefined'?globalThis:this);
