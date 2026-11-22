/* Future energy from the latest calculated curve; never from frozen history. */
(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory();
  else root.SolarRemaining=factory();
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const HOUR_MS=3600000;
  const date=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'});
  const dayKey=seconds=>date.format(new Date(seconds*1000));
  function dayEnd(seconds,day){
    // Use the site's calendar, including the 23-/25-hour DST days.
    let lo=Math.floor(seconds),hi=lo+26*3600;
    while(hi-lo>1){const mid=Math.floor((lo+hi)/2);if(dayKey(mid)===day)lo=mid;else hi=mid;}
    return hi;
  }
  function remainingToday(rows,nowMs=Date.now()){
    if(!Number.isFinite(nowMs))return {available:false,kWh:null,reason:'invalid-time'};
    const now=nowMs/1000,day=dayKey(now),end=dayEnd(now,day);
    const unavailable=reason=>({available:false,day,asOfMs:nowMs,kWh:null,reason});
    const today=rows.filter(r=>r.day===day).map(row=>{
      const duration=row.durationHours===undefined?300:row.durationHours*3600;
      return {row,duration,start:row.ts-duration/2,end:row.ts+duration/2};
    }).sort((a,b)=>a.start-b.start);
    if(!today.length)return unavailable('missing-day');
    let cursor=now,kWh=0;
    for(const bin of today){
      if(!Number.isFinite(bin.start)||!Number.isFinite(bin.end)||bin.duration<=0)return unavailable('invalid-interval');
      if(bin.end<=now||bin.start>=end)continue;
      if(!Number.isFinite(bin.row.power)||bin.row.power<0)return unavailable('invalid-power');
      if(bin.start>cursor+.001)return unavailable('incomplete-coverage');
      const from=Math.max(now,cursor,bin.start),to=Math.min(end,bin.end);
      if(to>from)kWh+=bin.row.power*(to-from)/3600;
      cursor=Math.max(cursor,Math.min(end,bin.end));
    }
    if(cursor<end-.001)return unavailable('incomplete-coverage');
    return {available:true,day,asOfMs:nowMs,dayEndSeconds:end,kWh:Math.max(0,kWh)};
  }
  function refreshDue(lastAttemptMs,nowMs=Date.now()){
    return !Number.isFinite(lastAttemptMs)||lastAttemptMs>nowMs+120000||
      Math.floor(lastAttemptMs/HOUR_MS)<Math.floor(nowMs/HOUR_MS);
  }
  function nextHourDelay(nowMs=Date.now()){
    return (Math.floor(nowMs/HOUR_MS)+1)*HOUR_MS-nowMs;
  }
  return {remainingToday,refreshDue,nextHourDelay};
});
