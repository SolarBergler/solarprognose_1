"""DOM20-Nahprofil je abgeleitetem Modulmittelpunkt, ohne Ertragskalibrierung.

Aufruf: python scripts/baue_modulnahprofil.py <DOM20.tif> <Nachbarkachel.tif>
Benötigt numpy und Pillow. TIFFs bleiben unverändert; Quellenhashes im Profil.
Algorithmus wie bisher: 150 m, 0.5 Grad, Ausschlusskreis 3 m, DOM + 0.3 m.
"""
import hashlib, json, math, sys, subprocess
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
def utm32(lat,lon):
    a=6378137;ee=.00669437999014;ep2=ee/(1-ee);k=.9996;p=math.radians(lat);lam=math.radians(lon-9)
    n=a/math.sqrt(1-ee*math.sin(p)**2);t=math.tan(p)**2;c=ep2*math.cos(p)**2;aa=math.cos(p)*lam
    m=a*((1-ee/4-3*ee**2/64-5*ee**3/256)*p-(3*ee/8+3*ee**2/32+45*ee**3/1024)*math.sin(2*p)+(15*ee**2/256+45*ee**3/1024)*math.sin(4*p)-(35*ee**3/3072)*math.sin(6*p))
    return (500000+k*n*(aa+(1-t+c)*aa**3/6+(5-18*t+t*t+72*c-58*ep2)*aa**5/120),k*(m+n*math.tan(p)*(aa*aa/2+(5-t+9*c+4*c*c)*aa**4/24+(61-58*t+t*t+600*c-330*ep2)*aa**6/720)))

def main(paths):
    c=json.loads((ROOT/'anlagenkonfiguration.json').read_text());mods=[m for p in c['panels'] for m in p['geo']['modulePositions']]
    xy=[utm32(m['latitude'],m['longitude']) for m in mods];tiles=[];sources=[]
    xmin=min(x for x,y in xy)-175;xmax=max(x for x,y in xy)+175;ymin=min(y for x,y in xy)-175;ymax=max(y for x,y in xy)+175
    for path in map(Path,paths):
        im=Image.open(path);sx,sy,_=im.tag_v2[33550];ox,oy=im.tag_v2[33922][3:5]
        if abs(sx-.2)>1e-6 or abs(sy-.2)>1e-6 or 25832 not in im.tag_v2[34735]:raise ValueError('DOM20 / EPSG:25832 erwartet')
        l=max(0,math.floor((xmin-ox)/sx));r=min(im.width,math.ceil((xmax-ox)/sx));t=max(0,math.floor((oy-ymax)/sy));b=min(im.height,math.ceil((oy-ymin)/sy))
        if l>=r or t>=b:continue
        z=np.asarray(im.crop((l,t,r,b)),dtype=np.float64);xx=ox+(np.arange(l,r)+.5)*sx;yy=oy-(np.arange(t,b)+.5)*sy
        tiles.append((xx,yy,z))
        sources.append(dict(file=path.name,url='https://download1.bayernwolke.de/a/dom20/DOM/'+path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),fileDate=im.tag_v2.get(306)))
    out=[];count=0
    for p in c['panels']:
        samples=[];heights=[]
        for m in p['geo']['modulePositions']:
            x,y=utm32(m['latitude'],m['longitude']);height=None
            for xx,yy,z in tiles:
                col=int(math.floor((x-xx[0]+.1)/.2));row=int(math.floor((yy[0]+.1-y)/.2))
                if 0<=row<len(yy) and 0<=col<len(xx):height=float(z[row,col])+.3;break
            if height is None or not -500<height<10000:raise ValueError('Keine Höhe am Modul '+m['id'])
            maxima=np.zeros(720);valid_count=0
            for xx,yy,z in tiles:
                dx=xx[None,:]-x;dy=yy[:,None]-y;d2=dx*dx+dy*dy
                valid=(d2<=150**2)&np.isfinite(z)&(z>-500)&(z<10000);valid_count+=int(valid.sum())
                mask=valid&(d2>9)&(z>height)
                rr,cc=np.nonzero(mask);dxx=xx[cc]-x;dyy=yy[rr]-y
                bins=np.floor((np.degrees(np.arctan2(dxx,dyy))+360)%360*2).astype(int)%720
                ang=np.degrees(np.arctan2(z[rr,cc]-height,np.sqrt(dxx*dxx+dyy*dyy)))
                np.maximum.at(maxima,bins,ang)
            if valid_count<math.pi*150**2/.04*.9:raise ValueError('Unvollständige DOM-Abdeckung')
            samples.append(np.round(np.clip(maxima,0,89),3).tolist());heights.append(height);count+=1
            if count%10==0:print(f'{count}/88 Modulmittelpunkte',flush=True)
        out.append(dict(name=p['name'],center={k:p['geo'][k] for k in ['latitude','longitude']},samples=samples,
                        sampleWeights=[m['wp'] for m in p['geo']['modulePositions']],
                        samplePositions=[dict(id=m['id'],latitude=m['latitude'],longitude=m['longitude'],wp=m['wp'],heightM=height) for m,height in zip(p['geo']['modulePositions'],heights)]))
    doc=dict(version=2,kind='dom20-nearshade',source='Bayerische Vermessungsverwaltung · DOM20 (CC BY 4.0)',
             location=dict(latitude=c['location']['latitude'],longitude=c['location']['longitude'],radius_m=150),panelProfiles=out,
             config=dict(panels=c['panels'],inverters=c['inverters']),meta=dict(generatedAt=datetime.now(timezone.utc).isoformat(),gridStepM=.2,sourceGridM=.2,
             samplesPerPanel=[len(p['samples']) for p in out],method='Ein DOM20-Horizont je abgeleitetem Modulmittelpunkt; Gewichtung nach Wp; 3-m-Ausschlusskreis wie bisher; keine elektrischen Zusatzverluste',
             placementAccuracy='Aus Belegung, Modulmaßen und GPS-Ankern abgeleitet; Fugen, Fensterlage im Raster und Garage-Einzelpositionen sind Näherungen.',license='CC BY 4.0',inputFiles=sources))
    doc['id']=hashlib.sha256(json.dumps(doc,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
    near=json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n';(ROOT/'nahverschattung.json').write_text(near)
    c['profiles']['near'].update(id=doc['id'],sha256=hashlib.sha256(near.encode()).hexdigest())
    # Geometriehash wird durch central-config.js gesetzt (gleiche kanonische Form).
    (ROOT/'anlagenkonfiguration.json').write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n')
    subprocess.run(['node','-e',"const fs=require('fs'),C=require('./central-config.js');(async()=>{const c=JSON.parse(fs.readFileSync('anlagenkonfiguration.json'));c.profiles.geometryHash=await C.sha256(C.canonical(C.geometry(c)));fs.writeFileSync('anlagenkonfiguration.json',C.serialize(c));await C.verifyBundle(C.serialize(c),fs.readFileSync('horizontprofil.json','utf8'),fs.readFileSync('nahverschattung.json','utf8'));})();"],cwd=ROOT,check=True)
    print('88 Horizonte erzeugt; Quellenhashes und Geometriebindung geprüft.',flush=True)

if __name__=='__main__':main(sys.argv[1:])
