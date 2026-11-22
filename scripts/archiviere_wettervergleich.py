#!/usr/bin/env python3
"""Capture simultaneous PV forecasts with three explicitly identified weather inputs."""
import argparse
import json
import math
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'prognosen'
LOCAL = ZoneInfo('Europe/Berlin')
FIRST_DAY = date(2026, 11, 23)
LAST_DAY = date(2026, 12, 13)
MODELS = {'mosmix': 'DWD MOSMIX-L', 'icon': 'DWD ICON-D2 Native', 'ifs': 'ECMWF IFS HRES',
          'best-match': 'Open-Meteo (Referenz)'}
API_MODELS = {'icon': 'dwd_icon_d2_native', 'ifs': 'ecmwf_ifs'}
FIELDS = ('shortwave_radiation', 'diffuse_radiation', 'direct_normal_irradiance', 'temperature_2m')
HOURLY_FIELDS = (*FIELDS, 'cloud_cover')
SLOTS = {'0 6 * * *': '06', '0 18 * * *': '18'}


def day_bounds(day):
    return tuple(int(datetime.combine(d, time(), LOCAL).timestamp()) for d in (day, day + timedelta(days=1)))


def parse_timestamp(text):
    result = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Zeitstempel ohne Zeitzone')
    return result


def forecast_window(slot, now):
    capture_day = now.date()
    target_day = capture_day + timedelta(days=slot == '18')
    if not FIRST_DAY <= target_day <= LAST_DAY:
        return None
    if not int(slot) <= now.hour < int(slot) + 2:
        raise ValueError(f'Kein gültiger {slot}-Uhr-Abruf: {now.isoformat()}')
    return capture_day, target_day


def run_times(model, slot, capture_day):
    # Conservative vintages available by both scheduled slots; keep ages reproducible.
    if model == 'icon':
        day, hour = capture_day, (0 if slot == '06' else 12)
    else:
        day = capture_day - timedelta(days=slot == '06')
        hour = 18 if slot == '06' else 6
    return datetime.combine(day, time(hour), timezone.utc)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def download_model(model, slot, capture_day, location):
    params = {
        'latitude': location['latitude'], 'longitude': location['longitude'],
        'hourly': ','.join(HOURLY_FIELDS), 'minutely_15': ','.join(FIELDS),
        'timezone': 'Europe/Berlin', 'timeformat': 'unixtime',
    }
    if model == 'best-match':
        issued = None
        url = 'https://api.open-meteo.com/v1/forecast?' + urlencode(dict(params, forecast_days=3))
    else:
        issued = run_times(model, slot, capture_day)
        params.update(models=API_MODELS[model], run=issued.strftime('%Y-%m-%dT%H:%M'),
                      forecast_hours=48, forecast_minutely_15=192)
        url = 'https://single-runs-api.open-meteo.com/v1/forecast?' + urlencode(params)
    with urlopen(url, timeout=18) as response:
        raw = response.read(300_001)
    if len(raw) > 300_000:
        raise ValueError('API-Antwort zu groß')
    doc = {
        'issuedAtUtc': issued.isoformat() if issued else None,
        'retrievedAtUtc': datetime.now(timezone.utc).isoformat(),
        'sourceUrl': url, 'responseSha256': sha256(raw).hexdigest(),
        'weather': json.loads(raw),
    }
    return doc


def read_mosmix(location, now):
    file = DATA / 'dwd_wetterstand.json'
    document = read_json(file)
    issued = parse_timestamp(document['issueTime'])
    captured = parse_timestamp(document['capturedAt'])
    if not timedelta(0) <= now - issued <= timedelta(hours=8):
        raise ValueError('MOSMIX-Modelllauf liegt außerhalb des zulässigen Abrufalters')
    if not -timedelta(minutes=1) <= now - captured <= timedelta(hours=2):
        raise ValueError('MOSMIX-Abruf ist für diesen Archivlauf nicht frisch')
    if any(abs(document[k] - location[k]) > 1e-5 for k in ('latitude', 'longitude')):
        raise ValueError('Abweichender MOSMIX-Standort')
    return {
        'issuedAtUtc': issued.isoformat(), 'retrievedAtUtc': captured.isoformat(),
        'station': document['station'], 'approximation': document['approximation'],
        'responseSha256': sha256(file.read_bytes()).hexdigest(), 'weather': document['weather'],
    }


def weather_for_day(weather, day, four_parts):
    start, end = day_bounds(day)
    normalized = {}
    for key, seconds, fields in [('hourly', 3600, HOURLY_FIELDS), ('minutely_15', 900, FIELDS)]:
        if key == 'minutely_15' and not four_parts:
            continue
        series = weather[key]
        times = series['time']
        if len(set(times)) != len(times) or any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError(f'Ungültiges Zeitraster ({key})')
        if not all(len(series[name]) == len(times) for name in fields):
            raise ValueError(f'Unvollständige Wetterfelder ({key})')
        index = {timestamp: i for i, timestamp in enumerate(times)}
        wanted = list(range(start + seconds, end + 1, seconds))
        out = {'time': wanted}
        for name in fields:
            selected = [series[name][index[t]] if t in index else None for t in wanted]
            for i, value in enumerate(selected):
                if value is None and key == 'minutely_15':
                    continue
                if value is None and key == 'hourly':
                    hour = datetime.fromtimestamp(wanted[i], LOCAL).hour
                    if hour <= 6 or hour >= 20:
                        continue
                if type(value) not in (float, int) or not math.isfinite(value):
                    raise ValueError(f'Fehlender oder ungültiger Wert für {name} bei {wanted[i]} ({key})')
                if name in FIELDS[:3] and value < 0:
                    raise ValueError(f'Negative Strahlung in {name}')
            out[name] = selected
        if key == 'hourly' and any(t not in index for t in wanted):
            raise ValueError('Keine vollständige stündliche Abdeckung')
        normalized[key] = out
    return normalized


def forecast_indicators(weather):
    h = weather['hourly']
    indices = [i for i, t in enumerate(h['time']) if 7 <= datetime.fromtimestamp(t, LOCAL).hour <= 17]
    ghi = sum(h['shortwave_radiation'][i] for i in indices)
    return {
        'meanCloudCoverPct': sum(h['cloud_cover'][i] for i in indices) / len(indices),
        'horizontalBeamShare': (sum(max(0, h['shortwave_radiation'][i] - h['diffuse_radiation'][i]) for i in indices) / ghi) if ghi else 0,
    }


def run_comparison(slot, now, output=None):
    interval = forecast_window(slot, now)
    if interval is None:
        print('Kein Zieltag im beauftragten Dreiwochenzeitraum.')
        return None
    capture_day, target_day = interval
    path = output or DATA / capture_day.isoformat() / f'wettervergleich-{slot}.json'
    if path.exists():
        print(f'Original bleibt erhalten: {path}')
        return path
    config = read_json(ROOT / 'anlagenkonfiguration.json')

    def load(model):
        try:
            source = (read_mosmix(config['location'], now) if model == 'mosmix'
                      else download_model(model, slot, capture_day, config['location']))
            if source['issuedAtUtc'] and parse_timestamp(source['issuedAtUtc']) > now:
                raise ValueError('Der Modelllauf liegt in der Zukunft')
            exact_weather = weather_for_day(source['weather'], target_day, model != 'mosmix')
            source['weather'] = exact_weather
            source['indicators'] = forecast_indicators(exact_weather)
            return model, {'name': MODELS[model], 'status': 'ok', **source}
        except Exception as exc:
            print(f'::warning title={MODELS[model]}:: {exc}')
            return model, {'name': MODELS[model], 'status': 'unavailable', 'reason': str(exc)}

    with ThreadPoolExecutor(max_workers=4) as pool:
        forecasts = dict(pool.map(load, MODELS))
    inputs = {model: data['weather'] for model, data in forecasts.items() if data['status'] == 'ok'}
    process = subprocess.run(
        ['node', str(ROOT / 'scripts' / 'wettermodell_rechenkern.cjs')],
        input=json.dumps({'day': target_day.isoformat(), 'forecasts': inputs}, allow_nan=False),
        text=True, capture_output=True, timeout=45, check=False, cwd=ROOT,
    )
    if process.returncode:
        raise RuntimeError('PV-Rechenlauf fehlgeschlagen: ' + process.stderr.strip())
    calculation = json.loads(process.stdout)
    calculated = calculation.pop('forecasts')
    start, end = day_bounds(target_day)
    for model in inputs:
        result = calculated.get(model)
        rows = result.get('rows') if result else None
        if (not rows or [row[0] for row in rows] != list(range(start + 150, end, 300))
                or any(not math.isfinite(row[1]) or row[1] < 0 for row in rows)
                or not math.isclose(result['powerKWh'], sum(row[1] / 12 for row in rows), abs_tol=1e-6)):
            raise RuntimeError(f'Unvollständige PV-Prognose für {model}')
        forecasts[model].update(result)
        print(f'{target_day} · {slot} · {MODELS[model]}: {result["powerKWh"]:.3f} kWh')
    save_json(path, {
        'schema': 1, 'captureDay': capture_day.isoformat(), 'targetDay': target_day.isoformat(),
        'slot': slot, 'capturedAtUtc': now.astimezone(timezone.utc).isoformat(),
        'timezone': str(LOCAL), **calculation, 'models': forecasts,
    })
    print(f'VERGLEICH GESPEICHERT: {path}')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', choices=('06', '18'))
    parser.add_argument('--output', type=Path, help='Lokale Testdatei außerhalb des regulären Archivpfads')
    args = parser.parse_args()
    slot = args.slot or SLOTS.get(os.environ.get('GITHUB_EVENT_SCHEDULE'))
    if slot is None:
        print('Manueller Workflow ohne Archivslot; reguläre Originale bleiben unangetastet.')
        return
    run_comparison(slot, datetime.now(LOCAL), args.output)


if __name__ == '__main__':
    main()
