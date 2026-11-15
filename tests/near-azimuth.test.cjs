'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../index.html'),'utf8');
const ctx={rad:Math.PI/180,deg:180/Math.PI};vm.createContext(ctx);
vm.runInContext(html.slice(html.indexOf('function utm32('),html.indexOf('async function readDomWindows(')),ctx);
test('UTM-Gitterrichtung wird vor dem Nahprofil auf geografisch Nord bezogen',()=>{
 assert.ok(Math.abs(ctx.utmGridConvergence(47.7,9))<1e-7);
 const lat=47.6978583,lon=11.8804056,g=ctx.utmGridConvergence(lat,lon);
 assert.ok(g>2.12&&g<2.14,g);
 const south=ctx.utm32(lat-.0001,lon),north=ctx.utm32(lat+.0001,lon);
 assert.equal(ctx.trueNorthBin(north.x-south.x,north.y-south.y,g),0);
 assert.equal(ctx.trueNorthBin(south.x-north.x,south.y-north.y,g),360);
 const west=ctx.utm32(lat,lon-.0001),east=ctx.utm32(lat,lon+.0001);
 assert.equal(ctx.trueNorthBin(east.x-west.x,east.y-west.y,g),180);
 assert.equal(ctx.trueNorthBin(west.x-east.x,west.y-east.y,g),540);
});
test('Halbgrad-Horizonte sind auf ihre Stützstellen zentriert und schließen bei Nord',()=>{
 const bearing=a=>ctx.trueNorthBin(Math.sin(a*Math.PI/180),Math.cos(a*Math.PI/180),0);
 assert.equal(bearing(.24),0);assert.equal(bearing(.26),1);
 assert.equal(bearing(359.9),0);assert.equal(bearing(179.9),360);
});
