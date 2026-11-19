/* Optional nine-point LiDAR shading for each physical module.
 * The old one-horizon-per-module schema remains valid and unchanged.
 * This is a GEOMETRIC area model: no optimizer data, string assumptions or fitted loss factors.
 */
(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory();
  else root.SolarNearArea=factory();
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const POINTS=9,BINS=720;
  const finiteAngle=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<90;
  function validate(profile,expected){
    if(profile.areaSamples===undefined)return false;
    const samples=profile.areaSamples;
    if(!Array.isArray(samples)||samples.length!==expected)
      throw Error('Neun-Punkte-Profile: falsche Modulanzahl');
    for(let k=0;k<expected;k++){
      const patches=samples[k];
      // Explicit null permits an individual module to fall back to its verified center profile.
      if(patches===null)continue;
      if(!Array.isArray(patches)||patches.length!==POINTS||
         patches.some(p=>!Array.isArray(p)||p.length!==BINS||p.some(v=>!finiteAngle(v))))
        throw Error('Neun-Punkte-Profile: ungueltiges Modul '+k);
    }
    return true;
  }
  function patches(profile,moduleIndex){
    return profile.areaSamples?.[moduleIndex]||null;
  }
  function visibleFraction(profile,moduleIndex,az,alt,mountain,nearAngle){
    const sources=patches(profile,moduleIndex);
    if(!sources)return Number(alt>=Math.max(mountain,nearAngle(profile.samples[moduleIndex],az)));
    let count=0;
    for(const patch of sources)
      if(alt>=Math.max(mountain,nearAngle(patch,az)))count++;
    return count/POINTS;
  }
  function diffuse(profile,moduleIndex,panel,nearDiffuseFactor){
    const sources=patches(profile,moduleIndex);
    if(!sources)return nearDiffuseFactor(panel,profile.samples[moduleIndex]);
    return sources.reduce((sum,patch)=>sum+nearDiffuseFactor(panel,patch),0)/POINTS;
  }
  return {POINTS,BINS,validate,visibleFraction,diffuse};
});
