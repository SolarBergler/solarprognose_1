"""Prospective snow-cover signal, separate from the four PV energy calculations."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import json
import math
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from dwd_mosmix import sun_altitude

LOCAL = ZoneInfo('Europe/Berlin')
RULE_ID = 'schnee-v1'
FIELDS = ('snowfall', 'temperature_2m', 'shortwave_radiation')
THRESHOLDS = {
    'freshSnowCm': 1.0,
    'maxSnowfallAirC': 1.0,
    'releaseAirC': 3.0,
    'sunnyReleaseMinAirC': 0.0,
    'sunnyReleaseGhiWm2': 250,
    'releaseHours': 2,
}


def fetch_icon_run(issued, location):
    query = urlencode({
        'latitude': location['latitude'], 'longitude': location['longitude'],
        'models': 'dwd_icon_d2_native', 'run': issued.strftime('%Y-%m-%dT%H:%M'),
        'hourly': ','.join(FIELDS), 'forecast_hours': 48, 'timeformat': 'unixtime',
        'timezone': str(LOCAL),
    })
    url = 'https://single-runs-api.open-meteo.com/v1/forecast?' + query
    with urlopen(url, timeout=10) as response:
        body = response.read(120_001)
    if len(body) > 120_000:
        raise ValueError('Schneedaten überschreiten das Antwortlimit')
    document = json.loads(body)
    if tuple(document['hourly_units'][key] for key in FIELDS) != ('cm', '°C', 'W/m²'):
        raise ValueError('Schneedaten haben unerwartete Einheiten')
    hourly = document['hourly']
    rows = list(zip(*(hourly[key] for key in ('time', *FIELDS)), strict=True))
    if any(a[0] >= b[0] for a, b in zip(rows, rows[1:])):
        raise ValueError('Schneestunden liegen nicht in zeitlicher Reihenfolge')
    return dict(
        issuedAtUtc=issued.isoformat(), retrievedAtUtc=datetime.now(timezone.utc).isoformat(),
        responseSha256=sha256(body).hexdigest(), sourceUrl=url, rows={r[0]: r[1:] for r in rows},
    )


def estimate_snow(target_day, slot, location, previous=None):
    day_before = target_day - timedelta(days=1)
    evening_run = datetime.combine(day_before, time(12), timezone.utc)
    sunrise_run = datetime.combine(target_day, time(0), timezone.utc)
    cutover = int(datetime.combine(target_day, time(6), LOCAL).timestamp())
    handoff = int(datetime.combine(day_before, time(13), LOCAL).timestamp())
    carry = (previous or {}).get('carryState') or {}
    has_history = (previous or {}).get('rule') == RULE_ID and carry.get('hourEndUtc') == handoff
    issued = [evening_run]
    if slot == '06':
        issued.append(sunrise_run)
    older_run = evening_run - timedelta(days=1)
    if not has_history:
        issued.insert(0, older_run)
    with ThreadPoolExecutor(max_workers=len(issued)) as pool:
        forecasts = dict(zip(issued, pool.map(lambda run: fetch_icon_run(run, location), issued), strict=True))
    # Preserve the snowfall signal from the preceding night when the 00 UTC run
    # begins after it. From 06:00 onwards use that newer run for the morning forecast.
    start = handoff + 3600
    if not has_history:
        start = int(datetime.combine(day_before - timedelta(days=1), time(14), LOCAL).timestamp())
    finish = int(datetime.combine(target_day, time(18), LOCAL).timestamp())
    next_handoff = int(datetime.combine(target_day, time(13), LOCAL).timestamp())
    next_state = None
    windows = []
    inputs = []
    accumulated = carry['coldSnowCm'] if has_history else 0.0
    clear_hours = carry['thawHours'] if has_history else 0
    for t in range(start, finish + 1, 3600):
        issue = older_run if t <= handoff else sunrise_run if slot == '06' and t > cutover else evening_run
        run = forecasts[issue]
        values = run['rows'].get(t)
        if not values or any(type(v) not in (float, int) or not math.isfinite(v) for v in values):
            raise ValueError(f'Schneewetter unvollständig für {datetime.fromtimestamp(t, LOCAL).isoformat()}')
        snow_cm, air_c, ghi = values
        if snow_cm < 0 or ghi < 0:
            raise ValueError('Negative Schneefall- oder Strahlungsmenge')
        snowing = snow_cm > 0 and air_c <= THRESHOLDS['maxSnowfallAirC']
        thawing = (air_c >= THRESHOLDS['releaseAirC']
                   or (air_c >= THRESHOLDS['sunnyReleaseMinAirC'] and ghi >= THRESHOLDS['sunnyReleaseGhiWm2']))
        if snowing:
            accumulated = round(accumulated + snow_cm, 6)
        covered = accumulated >= THRESHOLDS['freshSnowCm']
        clear_hours = min(clear_hours + 1, THRESHOLDS['releaseHours']) if thawing and not snowing else 0
        if clear_hours == THRESHOLDS['releaseHours']:
            accumulated = 0.0
        if t == next_handoff:
            next_state = {'hourEndUtc': t, 'coldSnowCm': accumulated, 'thawHours': clear_hours}
        inputs.append([t, snow_cm, air_c, ghi, run['issuedAtUtc']])
        if not covered or datetime.fromtimestamp(t - 1, LOCAL).date() != target_day:
            continue
        lit = [m for m in range(t - 3600, t, 300)
               if sun_altitude(m + 150, location['latitude'], location['longitude']) > 0]
        if not lit:
            continue
        first, last = lit[0], lit[-1] + 300
        if windows and windows[-1]['endUtc'] == first:
            windows[-1]['endUtc'] = last
        else:
            windows.append({'startUtc': first, 'endUtc': last})
    return {
        'status': 'ok', 'rule': RULE_ID, 'thresholds': THRESHOLDS,
        'expectedSnowOnModules': bool(windows), 'nearZeroWindows': windows,
        'carryState': next_state,
        'inputs': {'columns': ['hourEndUtc', 'snowfallCm', 'airC', 'ghiWm2', 'issuedAtUtc'], 'rows': inputs},
        'sourceRuns': [{k: v for k, v in run.items() if k != 'rows'} for run in forecasts.values()],
    }
