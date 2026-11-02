#!/usr/bin/env python3
"""DWD MOSMIX-L -> Open-Meteo-compatible hourly JSON for PV fallback.

Independent DWD download (no Open-Meteo dependency). DWD Rad1h is one-hour
GHI in kJ/m². Direct/diffuse splitting is an empirical Erbs approximation,
NOT official DWD direct/diffuse radiation. DO NOT use to silently replace
higher-resolution Open-Meteo irradiation when it is available.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent.parent
OUTPUT=ROOT/'prognosen'/'dwd_wetterstand.json'
STATION=ROOT/'prognosen'/'dwd_station.json'
LAT=float(os.environ.get('PV_LAT','47.69784444'))
LON=float(os.environ.get('PV_LON','11.88009722'))
BASE='https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/'
USER_AGENT='SolarprognoseSchliersee/1.0 (DWD MOSMIX-L non-commercial forecast backup)'
TZ=ZoneInfo('Europe/Berlin')


def tag(element):return element.tag.rsplit('}',1)[-1]


def download(url,limit=120_000_000):
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT})
    with urllib.request.urlopen(req,timeout=120) as resp:
        if resp.status!=200:raise RuntimeError(f'DWD HTTP {resp.status}')
        out=io.BytesIO()
        while True:
            b=resp.read(1_048_576)
            if not b:break
            out.write(b)
            if out.tell()>limit:raise RuntimeError('DWD-Datei überschreitet Sicherheitslimit')
    return out.getvalue()


def parse_series(node):
    values={}
    for f in node.iter():
        if tag(f)!='Forecast':continue
        param=next((v for k,v in f.attrib.items() if k.endswith('elementName')),None)
        if param not in ('Rad1h','TTT','N','Neff','SunD1'):continue
        child=next((ch for ch in f if tag(ch)=='value'),None)
        raw=(child.text if child is not None else f.text) or ''
        values[param]=[None if s=='-' else float(s) for s in raw.split()]
    return values


def placemark_coordinate(node):
    for el in node.iter():
        if tag(el)=='coordinates' and el.text:
            coords=el.text.strip().split()[0].split(',')
            if len(coords)>=2:return float(coords[1]),float(coords[0])
    return None


def haversine(lat1,lon1,lat2,lon2):
    a,b=math.radians(lat1),math.radians(lat2)
    dlat=b-a;dlon=math.radians(lon2-lon1)
    h=math.sin(dlat/2)**2+math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return 12742*math.asin(min(1,math.sqrt(h)))


def parse_kml(kml_stream,station_id=None):
    time_steps=[];issue=None;selected=None;best=float('inf')
    # IMPORTANT: stream the decompressed KML directly from ZipFile.open().
    # Never read the whole uncompressed all-stations KML into RAM.
    root=None
    for event,el in ET.iterparse(kml_stream,events=('start','end')):
        if root is None:root=el
        if event!='end':continue
        typ=tag(el)
        if typ=='IssueTime' and el.text:
            issue=el.text.strip()
        elif typ=='TimeStep' and el.text:
            time_steps.append(el.text.strip())
        elif typ=='Placemark':
            name=next((v.text.strip() for v in el.iter() if tag(v)=='name' and v.text),None)
            ident=el.attrib.get('id') or name or ''
            # The DWD placemark name is usually a station identifier (e.g. 10865).
            ids=[str(ident),str(name)]
            coords=placemark_coordinate(el)
            if coords is not None:
                lat,lon=coords
                distance=haversine(LAT,LON,lat,lon)
                matches=(station_id is None or station_id in ids)
                if matches and distance<best and len(time_steps)>0:
                    values=parse_series(el)
                    if 'Rad1h' in values and len(values['Rad1h'])==len(time_steps):
                        best=distance
                        selected={'id':str(name or ident),'latitude':lat,'longitude':lon,'distanceKm':round(distance,2),'values':values}
            el.clear()
            # No root.clear: in some KML, placemark elements and header share
            # the Document node; cleared placemarks release their large payload.
    if not selected:raise RuntimeError('Keine geeignete MOSMIX-Station mit Rad1h gefunden')
    if best>80:raise RuntimeError(f'Nächste MOSMIX-Station zu weit entfernt: {best:.1f} km')
    return time_steps,issue,selected


def sun_altitude(utc_seconds,lat=LAT,lon=LON):
    """NOAA approximate apparent solar altitude, enough for hourly Erbs split."""
    dt=datetime.fromtimestamp(utc_seconds,timezone.utc)
    day=dt.timetuple().tm_yday
    fractional=2*math.pi/365*(day-1+(dt.hour-12)/24+dt.minute/1440)
    eqtime=229.18*(.000075+.001868*math.cos(fractional)-.032077*math.sin(fractional)-.014615*math.cos(2*fractional)-.040849*math.sin(2*fractional))
    decl=.006918-.399912*math.cos(fractional)+.070257*math.sin(fractional)-.006758*math.cos(2*fractional)+.000907*math.sin(2*fractional)-.002697*math.cos(3*fractional)+.00148*math.sin(3*fractional)
    mins=dt.hour*60+dt.minute+dt.second/60+eqtime+4*lon
    hour_angle=math.radians((mins/4)%360-180)
    phi=math.radians(lat)
    return math.asin(max(-1,min(1,math.sin(phi)*math.sin(decl)+math.cos(phi)*math.cos(decl)*math.cos(hour_angle))))


def split_radiation(ghi,ts):
    """Estimate DHI + DNI from 1h GHI, preserving horizontal GHI energy."""
    dt=datetime.fromtimestamp(ts-1800,timezone.utc)  # previous-hour mean
    alt=sun_altitude(ts-1800)
    sine=max(0,math.sin(alt))
    if ghi<=0 or sine<=0.012:return max(0,ghi),0.0
    day=dt.timetuple().tm_yday
    ext=1367*(1+0.033*math.cos(2*math.pi*day/365))*sine
    kt=max(0,min(1.5,ghi/max(ext,1)))
    if kt<=0.22:kd=1-.09*kt
    elif kt<=0.8:kd=.9511-.1604*kt+4.388*kt**2-16.638*kt**3+12.336*kt**4
    else:kd=.165
    kd=max(.08,min(1,kd))
    dhi=ghi*kd
    dni=min(1300,max(0,(ghi-dhi)/sine))
    # If cap applied, ensure total still equals GHI by assigning remainder diffuse.
    dhi=max(0,ghi-dni*sine)
    return dhi,dni


def build_weather(times,issue,station):
    data=station['values'];rows=[]
    for i,iso in enumerate(times):
        dt=datetime.fromisoformat(iso.replace('Z','+00:00'))
        ts=int(dt.timestamp())
        rad=data['Rad1h'][i] if i<len(data['Rad1h']) else None
        if rad is None:
            # Missing overnight MOSMIX radiation is a zero, not an invented sunny hour.
            if sun_altitude(ts-1800)<math.radians(-2):rad=0
            else:continue
        if not 0<=rad<=5600:continue
        ghi=rad/3.6  # kJ/m² accumulated preceding hour => W/m² average
        dhi,dni=split_radiation(ghi,ts)
        temp=(data.get('TTT') or [None]*len(times))[i]
        cloud=(data.get('Neff') or data.get('N') or [None]*len(times))[i]
        rows.append((ts,ghi,dhi,dni, (temp-273.15 if temp is not None else 10.0),cloud if cloud is not None else 0))
    rows.sort()
    if len(rows)<48:raise RuntimeError(f'MOSMIX enthält nur {len(rows)} brauchbare Stundenwerte')
    now=int(datetime.now(timezone.utc).timestamp())
    future=sum(t>now for t,*_ in rows)
    if future<24:raise RuntimeError('MOSMIX-Vorhersage enthält zu wenige zukünftige Stunden')
    weather={'latitude':LAT,'longitude':LON,'timezone':'Europe/Berlin','utc_offset_seconds':3600,
      'hourly_units':{'direct_normal_irradiance':'W/m²','diffuse_radiation':'W/m²','shortwave_radiation':'W/m²','temperature_2m':'°C'},
      'hourly':{
        'time':[r[0] for r in rows],
        'shortwave_radiation':[round(r[1],2) for r in rows],
        'diffuse_radiation':[round(r[2],2) for r in rows],
        'direct_normal_irradiance':[round(r[3],2) for r in rows],
        'temperature_2m':[round(r[4],2) for r in rows],
        'cloud_cover':[round(r[5],1) for r in rows]}}
    return {'schema':1,'capturedAt':datetime.now(timezone.utc).isoformat(),'latitude':LAT,'longitude':LON,
      'source':'DWD MOSMIX-L (Rad1h, direkte/diffuse Strahlung mit Erbs angenähert)',
      'approximation':'Erbs diffuse fraction of measured-modelled GHI; not official DWD direct/diffuse',
      'issueTime':issue,'station':{k:v for k,v in station.items() if k!='values'},'weather':weather}


def obtain():
    station_id=None
    if STATION.exists():
        try:
            doc=json.loads(STATION.read_text())
            if abs(float(doc['latitude'])-LAT)<.0001 and abs(float(doc['longitude'])-LON)<.0001:
                station_id=doc['stationId']
        except (ValueError,KeyError,TypeError):pass
    attempted=[]
    for mode in (['single','all'] if station_id else ['all']):
        try:
            if mode=='single':url=f'{BASE}single_stations/{station_id}/kml/MOSMIX_L_LATEST_{station_id}.kmz'
            else:url=f'{BASE}all_stations/kml/MOSMIX_L_LATEST.kmz'
            print('Lade DWD MOSMIX:',url,flush=True)
            raw=download(url)
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names=[n for n in z.namelist() if n.lower().endswith('.kml')]
                if not names:raise RuntimeError('DWD KMZ enthält keine KML')
                # Stream decompression and XML parsing; uncompressed KML can exceed 1 GiB.
                with z.open(names[0]) as kml_stream:
                    times,issue,st=parse_kml(kml_stream,station_id if mode=='single' else None)
            result=build_weather(times,issue,st)
            return result
        except Exception as ex:
            attempted.append(f'{mode}: {ex}')
    raise RuntimeError('DWD MOSMIX nicht verfügbar: '+'; '.join(attempted))


def main():
    doc=obtain()
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    st=doc['station']
    STATION.write_text(json.dumps({'stationId':st['id'],'latitude':LAT,'longitude':LON,'stationLatitude':st['latitude'],'stationLongitude':st['longitude'],'stationDistanceKm':st['distanceKm']},indent=2)+'\n')
    print('DWD-Wetterdaten gespeichert:',OUTPUT,'Station',st['id'],st['distanceKm'],'km; Stundenwerte',len(doc['weather']['hourly']['time']))
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        print('DWD-Abruf fehlgeschlagen; KEINE Fake-Wetterdaten erzeugt:',e,file=sys.stderr)
        sys.exit(1)
