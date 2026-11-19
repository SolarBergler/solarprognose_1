"""Freeze the original weather-vintage input to an archived PV forecast.

No optimizer measurements or retrospectively observed weather enter this record.
The JSON is stored atomically as part of its corresponding forecast archive.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import math

REQUIRED = ('time', 'direct_normal_irradiance', 'diffuse_radiation', 'shortwave_radiation')
LOCAL = ZoneInfo('Europe/Berlin')


def build_snapshot(weather, diagnostics, local_day, slot, model_hash, central_hash):
    if not isinstance(weather, dict) or not isinstance(diagnostics, dict):
        raise ValueError('Missing weather input or diagnostics')
    if diagnostics.get('source') not in ('open-meteo','dwd') or diagnostics.get('notLive') is not False:
        raise ValueError('Weather is not a fresh supported forecast')
    if slot not in ('06','18') or not isinstance(model_hash, str) or not model_hash or not isinstance(central_hash, str) or not central_hash:
        raise ValueError('Missing slot or model configuration identity')
    day = date.fromisoformat(local_day)
    start = datetime(day.year, day.month, day.day, tzinfo=LOCAL).timestamp()
    end_day = day + timedelta(days=1)
    end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=LOCAL).timestamp()
    hourly = weather.get('hourly')
    if not isinstance(hourly, dict) or any(not isinstance(hourly.get(k),list) for k in REQUIRED):
        raise ValueError('Incomplete hourly weather arrays')
    times=hourly['time']
    if len(times)<6 or any(type(t) not in (int,float) or not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('Invalid hourly weather timestamps')
    if not any(start <= t < end for t in times):
        raise ValueError('Weather input has no values for archived day')
    for k,values in hourly.items():
        if k == 'time' or not isinstance(values,list):
            continue
        if len(values)!=len(times) or any(x is not None and (type(x) not in (int,float) or not math.isfinite(x)) for x in values):
            raise ValueError('Invalid hourly '+k)
    quarter=weather.get('minutely_15')
    if quarter is not None:
        if not isinstance(quarter,dict) or not isinstance(quarter.get('time'),list):
            raise ValueError('Invalid quarter-hour weather time array')
        qt=quarter['time']
        if any(type(t) not in (int,float) or not math.isfinite(t) for t in qt) or any(b<=a for a,b in zip(qt,qt[1:])):
            raise ValueError('Invalid quarter-hour timestamps')
        for k,values in quarter.items():
            if k == 'time' or not isinstance(values,list):
                continue
            if len(values)!=len(qt) or any(x is not None and (type(x) not in (int,float) or not math.isfinite(x)) for x in values):
                raise ValueError('Incomplete quarter-hour '+k)
    return {'schema':1,'source':diagnostics['source'],'sourceIssuedAtMs':diagnostics.get('issuedAt'),
            'day':local_day,'slot':slot,'modelHash':model_hash,'configurationHash':central_hash,
            'weather':weather}
