const test=require('node:test');
const assert=require('node:assert/strict');
const wr=require('../inverters.js');
const panel=(id,inverterId,kwp=5)=>({id,name:id,kwp,inverterId,az:165,tilt:30});
const inverter=(id,maxAcKw)=>({id,name:id,maxAcKw});
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-10,`${a} != ${b}`);

test('Ein Feld: obere AC-Grenze, keine zusätzliche Verlustannahme',()=>{
  const plan=wr.compileLimits([panel('p','w')],[inverter('w',6)]);
  near(wr.limitPower([5],plan).total,5);
  near(wr.limitPower([8],plan).total,6);
  near(wr.limitPower([8],plan).loss,2);
});
test('Gemeinsamer WR: zeitgleiche Leistungen statt Summe der kWp',()=>{
  const p=[panel('Garage','w',5.28),panel('Hütte','w',1.9)];
  const plan=wr.compileLimits(p,[inverter('w',6)]);
  const output=wr.limitPower([5.28,1.9],plan);
  near(output.total,6);near(output.loss,1.18);
  near(wr.limitPower([4,1],plan).loss,0);
  near(wr.limitPower([1,1.9],plan).total,2.9);
  near(wr.inverterSummary(inverter('w',6),p).dcKwp,7.18);
});
test('Mehrere Wechselrichter: freie Leistung kann nicht auf anderen WR übertragen werden',()=>{
  const plan=wr.compileLimits([panel('a','x'),panel('b','y')],[inverter('x',3),inverter('y',8)]);
  assert.deepEqual(wr.limitPower([7,2],plan).power,[3,2]);
  near(wr.limitPower([7,2],plan).loss,4);
});
test('Clipping vor Mittelung: zwei Minuten sind keine Begrenzung des Mittelwerts',()=>{
  const plan=wr.compileLimits([panel('a','x')],[inverter('x',6)]);
  near((wr.limitPower([10],plan).total+wr.limitPower([0],plan).total)/2,3);
});
test('Unvollständige Konfiguration erhält die bisherige Leistung vollständig',()=>{
  for(const max of [null,0,-1,NaN]){
    const plan=wr.compileLimits([panel('a','x')],[inverter('x',max)]);
    assert.equal(plan.configured,false);near(wr.limitPower([9],plan).total,9);
  }
  const plan=wr.compileLimits([panel('a',null),panel('b','x')],[inverter('x',1)]);
  assert.equal(plan.configured,false);near(wr.limitPower([9,9],plan).total,18);
});
test('Unbenutzte WR dürfen ohne Leistungsangabe bestehen bleiben',()=>{
  assert.equal(wr.compileLimits([panel('a','x')],[inverter('x',6),inverter('unused',null)]).configured,true);
});
test('Migration erhält alle Felder, Standort, Albedo und Systemverluste ohne erfundene Zuordnung',()=>{
  const settings={locationName:'Mein Ort',lat:47.7,lon:11.8,losses:12,albedo:.33,roofHeight:6,
    panels:[['Haus',14.225],['Garage',5.28],['Carport',9.9],['Hütte',1.9]].map(([name,kwp])=>({name,kwp,az:165,tilt:30}))};
  const migrated=wr.migratePlant(settings);
  assert.deepEqual(migrated.panels.map(p=>[p.name,p.kwp]),settings.panels.map(p=>[p.name,p.kwp]));
  assert.deepEqual(migrated.inverters.map(w=>[w.name,w.maxAcKw]),[['WR1',null],['WR2',null],['WR3',null],['WR4',null]]);
  assert.ok(migrated.panels.every(p=>p.inverterId===null));
  for(const key of ['locationName','lat','lon','losses','albedo','roofHeight'])assert.equal(migrated[key],settings[key]);
  assert.deepEqual(wr.migratePlant(migrated),migrated);
});
test('Stabile IDs und Modellkennung bei Umbenennung; neue Kennung bei AC- oder Zuordnungsänderung',()=>{
  const p=[panel('p','x')],w=[inverter('x',5),inverter('y',8)];
  const before=JSON.stringify(wr.modelConfiguration(p,w));
  w[0].name='Dachwechselrichter';
  assert.equal(JSON.stringify(wr.modelConfiguration(p,w)),before);
  w[0].maxAcKw=6;assert.notEqual(JSON.stringify(wr.modelConfiguration(p,w)),before);
  w[0].maxAcKw=5;p[0].inverterId='y';assert.notEqual(JSON.stringify(wr.modelConfiguration(p,w)),before);
});
test('Belegte WR können erst nach Neuzuordnung entfernt werden',()=>{
  const p=[panel('p','x')],w=[inverter('x',5),inverter('y',8)];
  assert.throws(()=>wr.removeInverter(w,p,'x'),/zuordnen/);
  p[0].inverterId='y';assert.deepEqual(wr.removeInverter(w,p,'x'),[w[1]]);
  assert.notEqual(wr.createId(),wr.createId());
});
test('Leistungsgrenzen und Energieerhaltung über viele zeitgleiche Feldkombinationen',()=>{
  const p=[panel('a','x'),panel('b','x'),panel('c','y')];
  const plan=wr.compileLimits(p,[inverter('x',6),inverter('y',3)]);
  for(let i=0;i<100;i++){
    const values=[i*.12,(99-i)*.08,i*.05],v=wr.limitPower(values,plan);
    assert.ok(v.power[0]+v.power[1]<=6+1e-10);assert.ok(v.power[2]<=3+1e-10);
    near(v.total+v.loss,values.reduce((s,x)=>s+x,0));
  }
});
