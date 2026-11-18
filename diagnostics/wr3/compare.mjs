/* Read-only WR3 optic/electrical discrepancy probe. No external dependencies.
   Usage: node diagnostics/wr3/compare.mjs /path/to/PV_SolarEdge_Kiosk_Ertraege.json
   Never commit the raw measurement file, serial numbers or full optimizer curves. */
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

export function analyze(archive, mask=null) {
  const runs=archive?.troubleshootingRuns||[];
  const powerRun=runs.find(r=>r.powerAnalysis?.sources?.outputPower?.rows?.length);
  const serialRun=runs.find(r=>r.analysis?.series?.length===24);
  if(!powerRun||!serialRun)throw Error('Original Optimiererleistungen oder verifizierte Seriennummer-Zuordnung fehlt');
  const pp=powerRun.powerAnalysis.sources.outputPower, vv=powerRun.powerAnalysis.sources.outputVoltage;
  const serials=serialRun.analysis.series.map(s=>s.serial);
  if(pp.rows.length!==vv.rows.length||serials.length!==24)throw Error('Nicht zuordenbare Messraster');
  for(const [source,name] of [[pp,'power'],[vv,'voltage']]){
    const headers=source.headers.slice(1).map(h=>h.split(' - ').at(-1));
    if(JSON.stringify(headers)!==JSON.stringify(serials))throw Error('Spalten/Modulzuordnung stimmt nicht: '+name);
  }
  const numeric=(v)=>v!==null&&v!==undefined&&Number.isFinite(v);
  const daytime=s=>Number(s.slice(11,13))*60+Number(s.slice(14,16));
  const strong=new Set();
  for(let i=0;i<18;i++)for(const row of pp.rows){
    const t=daytime(row.time);
    if(t>=615&&t<=655&&numeric(row.values[i])&&row.values[i]>=150)strong.add(i);
  }
  const cases=[];
  let paired=0,eligible=0;
  for(let ri=0;ri<pp.rows.length;ri++){
    const a=pp.rows[ri],v=vv.rows[ri];
    if(a.time!==v.time||!a.time.startsWith('2026-11-14')||a.values.length!==24||v.values.length!==24)
      throw Error('Messreihe beschädigt, Tag/Zeitstempel oder Modulanzahl unerwartet');
    const minute=daytime(a.time);
    if(minute<555||minute>840)continue;
    const references=[];
    for(let i=0;i<18;i++)if(numeric(a.values[i])&&numeric(v.values[i])&&
      v.values[i]>=0&&v.values[i]<79.5&&a.values[i]>=130)references.push([i,a.values[i]]);
    for(const j of strong){
      const power=a.values[j],voltage=v.values[j];
      if(!numeric(power)||!numeric(voltage))continue;
      paired++;
      const peers=references.filter(x=>x[0]!==j).map(x=>x[1]);
      if(!peers.length)continue;
      eligible++;
      const peer=Math.max(...peers);
      if(power>=0&&power<.25*peer&&voltage>=0&&voltage<75){
        const sample={time:a.time,moduleId:serialRun.analysis.series[j].moduleId,
          measuredW:power,optimizerV:voltage,referenceW:peer,relativePower:power/peer};
        if(mask) {
          if(mask.day!=='2026-11-14'||mask.time_start!=='09:00'||mask.time_step_min!==5||
             mask.hex.length%6!==0)throw Error('Nicht passender Schattenmodell-Snapshot');
          const mi=(minute-540)/5;
          sample.modelDirectSun=Number.isInteger(mi)&&mi>=0&&mi<mask.hex.length/6?
            Boolean((Number.parseInt(mask.hex.slice(mi*6,mi*6+6),16)&(1<<j))):null;
        }
        cases.push(sample);
      }
    }
  }
  const conflicts=cases.filter(x=>x.modelDirectSun===true);
  return {day:'2026-11-14',caseDefinition:'Trina 400 Wp, >150 W in morning, same-type peer >=130 W / <79.5 V, module <25% peer / <75 V',
    counts:{exportRows:pp.rows.length,referenceModules:strong.size,validPaired:paired,eligible,
      suspected:cases.length,modelDirectSunConflicts:mask?conflicts.length:null,
      conflictTimestamps:mask?new Set(conflicts.map(x=>x.time)).size:null,
      conflictModules:mask?new Set(conflicts.map(x=>x.moduleId)).size:null},cases};
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href){
  const archivePath=process.argv[2];
  if(!archivePath)throw Error('Usage: node diagnostics/wr3/compare.mjs /path/to/PV_SolarEdge_Kiosk_Ertraege.json');
  const archive=JSON.parse(fs.readFileSync(archivePath,'utf8'));
  const mask=JSON.parse(fs.readFileSync(new URL('./dom20-mask-2026-11-14.json',import.meta.url),'utf8'));
  const result=analyze(archive,mask);
  console.log(JSON.stringify(result,null,2));
}
