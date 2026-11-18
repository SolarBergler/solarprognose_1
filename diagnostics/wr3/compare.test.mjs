import test from 'node:test';
import assert from 'node:assert/strict';
import {analyze} from './compare.mjs';

test('Nur validierte echte Modul-Zeit-Messpaare und DOM20-Widerspruch',()=>{
 const series=Array.from({length:24},(_,i)=>({moduleId:'3.1.'+(i+1),serial:'TEST'+(i+1)}));
 const headers=['Zeitstempel',...series.map(x=>'Output Power (W) - '+x.serial)];
 const vHeaders=['Zeitstempel',...series.map(x=>'Output Voltage (V) - '+x.serial)];
 const row=(time,ps,vs)=>[{time,values:ps},{time,values:vs}];
 const ps=Array(24).fill(null),vs=Array(24).fill(null);
 const warm=row('2026-11-14T10:30:00+01:00',ps.map((_,i)=>i===8||i===9?220:i===10?240:null),
   vs.map((_,i)=>i===8||i===9||i===10?40:null));
 const cool=row('2026-11-14T12:30:00+01:00',ps.map((_,i)=>i===8?21:i===9?16:i===10?170:null),
   vs.map((_,i)=>i===8?10:i===9?8.5:i===10?74:null));
 const archive={troubleshootingRuns:[
  {analysis:{series}},
  {powerAnalysis:{sources:{outputPower:{headers,rows:[warm[0],cool[0]]},outputVoltage:{headers:vHeaders,rows:[warm[1],cool[1]]}}}}
 ]};
 const bits=Array(79).fill('000000');
 bits[42]=( (1<<8)|(1<<9)).toString(16).padStart(6,'0');
 const mask={day:'2026-11-14',time_start:'09:00',time_step_min:5,hex:bits.join('')};
 const result=analyze(archive,mask);
 assert.equal(result.counts.referenceModules,3);
 assert.equal(result.counts.suspected,2);
 assert.equal(result.counts.modelDirectSunConflicts,2);
 assert.equal(result.counts.conflictTimestamps,1);
 const noVolts=structuredClone(archive);
 noVolts.troubleshootingRuns[1].powerAnalysis.sources.outputVoltage.rows[1].values[8]=null;
 assert.equal(analyze(noVolts,mask).counts.suspected,1);
});
