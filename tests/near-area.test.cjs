'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const AREA=require('../near-area.js');
const C=require('../central-config.js');

const flat=height=>Array(720).fill(height);
const makeProfile=()=>({samples:[flat(15),flat(20)],sampleWeights:[300,450]});
const nearAngle=(arr,az)=>arr[Math.floor(((az%360)+360)%360*2)%720];
const diffuse=(panel,sample)=>sample[0]/100;
test('One-center profiles retain the exact V12 binary visibility and diffuse outcome',()=>{
  const profile=makeProfile();
  assert.equal(AREA.validate(profile,2),false);
  for(const alt of [0,5,15,17,20,30])for(let k=0;k<2;k++){
    const old=Number(alt>=Math.max(10,nearAngle(profile.samples[k],180)));
    assert.equal(AREA.visibleFraction(profile,k,180,alt,10,nearAngle),old);
    assert.equal(AREA.diffuse(profile,k,{},diffuse),diffuse({},profile.samples[k]));
  }
});
test('Nine equal surface patches represent area-visible fraction without optimizer data',()=>{
  const profile=makeProfile();
  profile.areaSamples=[
    [flat(10),flat(10),flat(10),flat(25),flat(25),flat(25),flat(25),flat(25),flat(25)],
    null
  ];
  assert.equal(AREA.validate(profile,2),true);
  assert.ok(Math.abs(AREA.visibleFraction(profile,0,180,15,0,nearAngle)-1/3)<1e-12);
  assert.equal(AREA.visibleFraction(profile,0,180,9,0,nearAngle),0);
  assert.equal(AREA.visibleFraction(profile,0,180,26,0,nearAngle),1);
  assert.equal(AREA.visibleFraction(profile,1,180,15,0,nearAngle),0);
  assert.ok(Math.abs(AREA.diffuse(profile,0,{},diffuse)-.2)<1e-12);
  assert.equal(AREA.diffuse(profile,1,{},diffuse),.2);
});
test('Reject incomplete area profiles, missing modules, and nonphysical angles',()=>{
  const profile=makeProfile();
  const malformed=[
    [],[null],[[flat(10)] ,null],
    [Array.from({length:9},()=>Array(719).fill(0)),null],
    [Array.from({length:9},()=>flat(90)),null],
    [Array.from({length:9},()=>flat(NaN)),null],
  ];
  for(const data of malformed){
    profile.areaSamples=data;
    assert.throws(()=>AREA.validate(profile,2));
  }
});
test('Central configuration rejects invalid nine-point profiles and accepts missing area data',()=>{
  const config=JSON.parse(fs.readFileSync(path.join(__dirname,'../anlagenkonfiguration.json')));
  const near=JSON.parse(fs.readFileSync(path.join(__dirname,'../nahverschattung.json')));
  const p=config.panels[0],profile=structuredClone(near.panelProfiles[0]);
  assert.doesNotThrow(()=>C.verifyPanelProfile(p,profile));
  profile.areaSamples=Array(profile.samples.length).fill(null);
  profile.areaSamples[0]=Array.from({length:9},()=>flat(12));
  assert.doesNotThrow(()=>C.verifyPanelProfile(p,profile));
  profile.areaSamples[0][3][100]=90;
  assert.throws(()=>C.verifyPanelProfile(p,profile),/Neun-Punkte/);
});
test('Index references the area library before the main inline application',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
  assert.ok(html.includes('<script src="./near-area.js?v=12.9.11"></script>'));
  assert.ok(html.includes('AREA.visibleFraction('));
  assert.ok(html.includes('AREA.diffuse('));
  assert.ok(html.indexOf('src="./near-area.js')<html.indexOf('const AREA=window.SolarNearArea'));
});
