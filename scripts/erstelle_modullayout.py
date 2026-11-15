"""Bestätigte Bestückung und abgeleitete Modulmittelpunkte (15.11.2026).

Kein Ertrags-Fitting: Maße aus Herstellerdatenblättern, Anordnung aus SolarEdge,
GPS-Anker vom Betreiber. Fugen und Fensterpositionen im Belegungsraster sind
Näherungen; nicht als vermessene Einzelmodulkoordinaten behandeln.
"""
import copy, json, math
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GAP=.025  # Arbeitsannahme, kein vom Betreiber vermessener Fugenabstand.

def offset(lat,lon,east,north):
    a=6378137;e2=.00669437999014;p=math.radians(lat)
    n=a/math.sqrt(1-e2*math.sin(p)**2);m=a*(1-e2)/(1-e2*math.sin(p)**2)**1.5
    return lat+math.degrees(north/m),lon+math.degrees(east/(n*math.cos(p)))

def place(panel,items,anchor,source):
    r=panel['referencePoint'];az=math.radians(panel['az']);tilt=math.radians(panel['tilt'])
    modules=[]
    for ident,x,y,group in items:
        g=panel['moduleGroups'][group];d=g['dimensionsMm'];portrait=g.get('mounting')=='portrait'
        w=(d['width'] if portrait else d['length'])/1000
        dep=(d['length'] if portrait else d['width'])/1000
        dx=x-anchor[0];dy=(y-anchor[1])*math.cos(tilt)
        east=-dx*math.cos(az)+dy*math.sin(az);north=dx*math.sin(az)+dy*math.cos(az)
        lat,lon=offset(r['latitude'],r['longitude'],east,north)
        modules.append(dict(id=ident,latitude=lat,longitude=lon,wp=g['wp'],groupIndex=group,
                            width_m=w,depth_m=dep,roofX_m=round(dx,5),roofY_m=round(y-anchor[1],5)))
    panel['geo']['modulePositions']=modules
    panel['geo']['latitude']=sum(m['latitude'] for m in modules)/len(modules)
    panel['geo']['longitude']=sum(m['longitude'] for m in modules)/len(modules)
    xmin=min(m['roofX_m']-m['width_m']/2 for m in modules);xmax=max(m['roofX_m']+m['width_m']/2 for m in modules)
    ymin=min(m['roofY_m']-m['depth_m']/2 for m in modules);ymax=max(m['roofY_m']+m['depth_m']/2 for m in modules)
    panel['geo'].update(name=panel['name'],azimuth=panel['az'],tilt_deg=panel['tilt'],width_m=round(xmax-xmin,5),depth_m=round((ymax-ymin)*math.cos(tilt),5))
    panel['layoutSurvey']=dict(status='derived-approximate',source=source,gapAssumptionM=GAP,
        anchorRoofX_m=anchor[0],anchorRoofY_m=anchor[1],
        note='Modulmaße und Bestückung bestätigt; Einzelpositionen aus Belegungsraster und GPS-Anker abgeleitet, nicht vermessen. Fensterfreiräume und Fugenabstände sind Näherungen.')

def main():
    path=ROOT/'anlagenkonfiguration.json';c=json.loads(path.read_text());by={p['name']:p for p in c['panels']}
    if any(p['name']=='Garage Ost' for p in c['panels']):raise SystemExit('Layout bereits erzeugt; Ausgangskonfiguration verwenden.')
    p=by['Haus links'];px=1.640+GAP;py=.992+GAP
    rows=[[9,10,13,14,23,24],[8,11,12,15,22],[7,None,None,16,21],[6,None,None,17,20],[None,None,None,None,19],[None,None,None,None,18]]
    items=[(f'4.1.{n}',col*px,row*py,0) for row,nums in enumerate(rows) for col,n in enumerate(nums) if n]
    for k in range(5):items.append((f'4.1.{k+1}',-.820+.519+k*(1.038+GAP),3*py+.496+GAP+2.094/2,1))
    place(p,items,(2*px,2.5*py),'SolarEdge-Belegung Haus links; Bezugspunkt rechtes der beiden Dachfenster neben dem Kamin')
    p=by['Haus rechts'];ja=3*px+.820+GAP+2.015/2
    items=[]
    for row,col,num in [(0,1,1),(0,2,2),(0,3,3),(1,3,4),(2,3,19),(3,3,18),(4,0,14),(4,1,15),(4,2,16),(4,3,17),(5,0,13),(5,1,12),(5,2,11),(5,3,10)]:items.append((f'1.1.{num}',col*px,row*py,0))
    for row,num in [(0,6),(1,5)]:items.append((f'1.1.{num}',ja,row*py,1))
    for row,num in [(2,7),(3,8),(4,9)]:items.append((f'1.1.{num}',ja+2.015+GAP,row*py,1))
    place(p,items,(ja,2.5*py),'SolarEdge-Belegung Haus rechts; Bezugspunkt oberes Dachfenster zwischen den fünf JA-Solar-Modulen')
    p=by['Carport'];px=1.754+GAP;py=1.096+GAP
    # Nummerierung aus dem SolarEdge-Belegungsplan (3.1.1 bis 3.1.24).
    rows=[[4,5,8,9,12,13],[3,6,7,10,11,14],[2,1,18,17,16,15]]
    items=[(f'3.1.{n}',col*px,row*py,0) for row,nums in enumerate(rows) for col,n in enumerate(nums)]
    right=5*px+1.754/2
    for k in range(6):items.append((f'3.1.{19+k}',right-6*1.038-5*GAP+1.038/2+k*(1.038+GAP),2*py+1.096/2+GAP+2.094/2,1))
    place(p,items,(2.5*px,py),'SolarEdge-Belegung Carport; GPS-Mitte ausschließlich des oberen 3×6-Feldes')
    p=by['Hütte vorne'];p['moduleGroups'][0]['mounting']='portrait'
    # Fünf Module in einer Nord-Süd-Reihe, gemeinsam nach Westen.
    items=[(f'2.1.{17+k}',(k-2)*(1.029+GAP),0,0) for k in range(5)]
    place(p,items,(0,0),'SolarEdge-Belegung Hütte; GPS-Mitte des mittleren Moduls')
    p=by['Garage'];full=copy.deepcopy(p);p['kwp']=4.62;p['moduleGroups']=p['moduleGroups'][:2]
    px=1.705+GAP;py=1.028+GAP
    rows=[[14,13,12,10,7,6],[None,None,11,9,8,5],[None,None,1,2,3,4]]
    items=[(f'2.1.{n}',col*px,row*py,0 if col>=2 else 1) for row,nums in enumerate(rows) for col,n in enumerate(nums) if n]
    place(p,items,(3.5*px,py),'SolarEdge-Belegung Garage; GPS-Mitte des 3×4-Hauptblocks; zwei Zusatzmodule links')
    extra=[]
    for facing,az in [('east',90),('west',270)]:
        q=copy.deepcopy(full);q['id']='panel-garage-'+facing;q['name']='Garage '+('Ost' if facing=='east' else 'West');q['kwp']=.33;q['az']=az;q['tilt']=20
        q['moduleGroups']=[copy.deepcopy(next(g for g in full['moduleGroups'] if g.get('facing')==facing))]
        q['moduleGroups'][0].update(tiltDeg=20,tiltApproximate=True,azimuthDeg=az,azimuthApproximate=True)
        # Kein unbelegtes Zuordnen der Optimierernummern 2.1.15/16 zu Ost/West:
        # beide Orientierungen verwenden vorläufig die Mitte des separaten Paares.
        dx=.0-3.5*px;dy=(5.0*py-py)*math.cos(math.radians(30));a=math.radians(165)
        lat,lon=offset(full['referencePoint']['latitude'],full['referencePoint']['longitude'],-dx*math.cos(a)+dy*math.sin(a),dx*math.sin(a)+dy*math.cos(a))
        q['referencePoint']=dict(latitude=lat,longitude=lon,kind='derived_pair_center',description='Abgeleitete Mitte des separaten Ost-/West-Paares unterhalb der Garage',dms='Aus bestätigtem Garage-Anker abgeleitet',confirmedOn='2026-11-15')
        place(q,[(q['id'],0,0,0)],(0,0),'Je ein Ost- und Westmodul mit ca. 20° vom Betreiber bestätigt; Paarposition aus SolarEdge-Schema geschätzt')
        q['layoutSurvey']['note']='Ca. 20° Neigung bestätigt; Azimut 90°/270° aus Ost/West abgeleitet. Einzelzuordnung der Positionen 2.1.15/16 zu Ost/West unbekannt; gemeinsame geschätzte Paarmitte, keine vorgetäuschte Nummernzuordnung.'
        extra.append(q)
    c['panels'].extend(extra);c['updatedAt']=datetime.now(timezone.utc).isoformat();c['revision']=3
    assert sum(len(p['geo']['modulePositions']) for p in c['panels'])==88
    assert abs(sum(p['kwp'] for p in c['panels'])-31.305)<1e-9
    for p in c['panels']:
        assert abs(sum(m['wp'] for m in p['geo']['modulePositions'])/1000-p['kwp'])<1e-9
    path.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n')
    print('88 Modulpositionen in 7 Ausrichtungsgruppen; 31.305 kWp; Näherungen dokumentiert.')

if __name__=='__main__':main()
