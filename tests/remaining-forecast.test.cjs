const test=require('node:test'),assert=require('node:assert/strict');
const R=require('../remaining-forecast.js');
const key=seconds=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(seconds*1000));
function rows(from,to,power=1){
 const a=Date.parse(from)/1000,b=Date.parse(to)/1000,result=[];
 for(let t=a;t<b;t+=300)result.push({ts:t+150,day:key(t+150),power:typeof power==='function'?power(t):power,durationHours:1/12});
 return result;
}
const day=()=>rows('2026-11-21T00:00:00+01:00','2026-11-22T00:00:00+01:00',2);
test('Only future energy, including the remaining half of the current five-minute bin',()=>{
 const data=[...rows('2026-11-20T00:00:00+01:00','2026-11-21T00:00:00+01:00',50),...day(),...rows('2026-11-22T00:00:00+01:00','2026-11-23T00:00:00+01:00',100)];
 const r=R.remainingToday(data,Date.parse('2026-11-21T12:02:30+01:00'));
 assert.equal(r.available,true);assert.equal(r.day,'2026-11-21');assert.ok(Math.abs(r.kWh-2*(11+57.5/60))<1e-9);
});
test('A complete zero forecast after the production window is a valid zero',()=>{
 const data=rows('2026-11-21T00:00:00+01:00','2026-11-22T00:00:00+01:00',t=>new Date(t*1000).getUTCHours()<15?2:0);
 assert.equal(R.remainingToday(data,Date.parse('2026-11-21T18:00:00+01:00')).kWh,0);
});
test('A missing day, a future gap or truncated day must not be shown as zero',()=>{
 const now=Date.parse('2026-11-21T12:00:00+01:00');
 assert.equal(R.remainingToday([],now).available,false);
 assert.equal(R.remainingToday(day().filter((r,i)=>i!==150),now).reason,'incomplete-coverage');
 assert.equal(R.remainingToday(day().slice(0,150),now).available,false);
});
test('Unusable future powers and invalid time are unavailable',()=>{
 const data=day();data[150].power=NaN;
 assert.equal(R.remainingToday(data,Date.parse('2026-11-21T12:00:00+01:00')).reason,'invalid-power');
 assert.equal(R.remainingToday(day(),NaN).available,false);
});
test('Spring and autumn clock changes retain the actual 23-/25-hour site day',()=>{
 for(const [from,to,hours] of [['2026-03-29T00:00:00+01:00','2026-03-30T00:00:00+02:00',23],['2026-10-25T00:00:00+02:00','2026-10-26T00:00:00+01:00',25]]){
  const r=R.remainingToday(rows(from,to),Date.parse(from));assert.equal(r.available,true);assert.ok(Math.abs(r.kWh-hours)<1e-9);
 }
});
test('The site day changes at Berlin midnight, including while the device is elsewhere',()=>{
 const r=R.remainingToday(rows('2026-11-23T00:00:00+01:00','2026-11-24T00:00:00+01:00'),Date.parse('2026-11-22T23:30:00Z'));
 assert.equal(r.day,'2026-11-23');assert.ok(Math.abs(r.kWh-23.5)<1e-9);
});
test('Refresh is due at the next full hour, not each minute or on every focus event',()=>{
 const at=s=>Date.parse('2026-11-21T'+s+'+01:00'),last=at('11:20:00');
 assert.equal(R.refreshDue(null,last),true);
 assert.equal(R.refreshDue(last,at('11:59:59')),false);assert.equal(R.refreshDue(last,at('12:00:00')),true);
 assert.equal(R.refreshDue(at('12:00:00'),at('12:00:01')),false);
 assert.equal(R.nextHourDelay(at('11:20:00')),40*60000);assert.equal(R.nextHourDelay(at('12:00:00')),3600000);
});
