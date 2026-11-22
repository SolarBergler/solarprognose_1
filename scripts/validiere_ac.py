#!/usr/bin/env python3
"""Prueft archivierte PV-Prognosen gegen AC-Tagesertraege, ohne Optimiererdaten.

Eingabe: CSV mit date,ac_kwh (optional wr1_kwh .. wr4_kwh), oder
          JSON-Archiv mit SolarEdge-dailyEnergy,
          unveraenderte Archivdateien prognosen/YYYY-MM-DD/06.json (oder 18.json).
Gruppiert nach Programmversion, Modell- und Physik-Hash. Kein Rueckgriff auf nachtraegliches Wetter.
"""
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from solaredge_ac import load_kiosk_ac

LOCAL = ZoneInfo('Europe/Berlin')

def nonnegative(value, context):
    try:
        number = float(value.strip().replace(',', '.')) if isinstance(value, str) else float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{context}: keine Zahl') from None
    if not math.isfinite(number) or number < 0:
        raise ValueError(f'{context}: negativer oder nicht endlicher Wert')
    return number


def observations(path):
    if path.suffix.lower() == '.json':
        return load_kiosk_ac(path)
    with path.open(encoding='utf-8-sig', newline='') as fp:
        sample = fp.read(2048); fp.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fp, dialect=dialect)
        if not reader.fieldnames or not {'date', 'ac_kwh'} <= set(reader.fieldnames):
            raise ValueError('CSV benoetigt die Spalten date,ac_kwh')
        result = {}
        for row in reader:
            day = date.fromisoformat(row['date']).isoformat()
            if day in result:
                raise ValueError('Doppelt gemessener Tag: ' + day)
            value = {'ac_kwh': nonnegative(row['ac_kwh'], day + ' AC')}
            status = (row.get('status') or 'final').strip().lower()
            if status not in ('final', 'reported', 'provisional'):
                raise ValueError(day + ': ungueltiger Messwertstatus')
            value['status'] = status
            for i in range(1, 5):
                label = f'wr{i}_kwh'
                if label in row and row[label] not in ('', None):
                    value[label] = nonnegative(row[label], day + ' ' + label)
            result[day] = value
    if not result:
        raise ValueError('Keine Messdaten vorhanden')
    return result


def archive_record(path, slot):
    doc = json.loads(path.read_text(encoding='utf-8'))
    day = date.fromisoformat(path.parent.name).isoformat()
    if doc.get('day') != day or doc.get('slot') != slot:
        raise ValueError(f'{path}: falscher Tag oder Prognoseslot')
    time = datetime.fromisoformat(doc['recordedAt'].replace('Z', '+00:00'))
    if time.tzinfo is None:
        raise ValueError(f'{path}: recordedAt ohne Zeitzone')
    local = time.astimezone(LOCAL)
    expected = 6 if slot == '06' else 18
    if local.date().isoformat() != day or not expected <= local.hour < expected + 2:
        raise ValueError(f'{path}: keine gueltige {slot}-Uhr-Prognose')
    model = doc.get('modelHash')
    central = doc.get('centralConfiguration')
    physical = central.get('physicalHash') if isinstance(central, dict) else None
    if not isinstance(model, str) or not model:
        raise ValueError(f'{path}: Modellkennung fehlt')
    if central is not None and (not isinstance(physical, str) or not physical):
        raise ValueError(f'{path}: Physikkennung der zentralen Konfiguration fehlt')
    if doc.get('weatherDiagnostics', {}).get('notLive'):
        raise ValueError(f'{path}: nicht-live Wetterstatus, kein gueltiges Prognose-Sample')
    result = {'date': day, 'slot': slot, 'model_hash': model,
              'physical_hash': physical, 'version': doc.get('modelVersion', ''),
              'near_id': doc.get('nearProfileId', ''),
              'forecast_ac_kwh': nonnegative(doc.get('powerKWh'), str(path)),
              'snapshot': str(path)}
    # Optional: WR-Leistung nur aus Feldsummen; nie aus Optimiererdaten.
    panels = doc.get('inverterConfiguration', {}).get('panels', [])
    sums = doc.get('byPanel', [])
    by_name = {p.get('name'): p.get('inverterId') for p in panels}
    by_wr = defaultdict(float)
    if panels and sums and len(sums) == len(panels) and all(p.get('name') in by_name for p in sums):
        for p in sums:
            name = by_name[p['name']]
            if name and name.startswith('wr-'):
                by_wr[name] += nonnegative(p.get('kWh'), str(path) + '/' + p['name'])
        for i in range(1, 5):
            if f'wr-{i}' in by_wr:
                result[f'forecast_wr{i}_kwh'] = by_wr[f'wr-{i}']
    return result


def score(rows, prefix='ac_'):
    errors = [r[f'forecast_{prefix}kwh'] - r[f'actual_{prefix}kwh'] for r in rows]
    actual = sum(r[f'actual_{prefix}kwh'] for r in rows)
    n = len(errors)
    return {'n': n, 'mae_kwh': sum(map(abs, errors)) / n,
            'bias_kwh': sum(errors) / n,
            'rmse_kwh': math.sqrt(sum(e*e for e in errors) / n),
            'wape_percent': 100 * sum(map(abs, errors)) / actual if actual else None}


def evaluate(archive_dir, actuals, slot='06', min_days=5, include_provisional=False):
    if slot not in ('06', '18') or min_days < 1:
        raise ValueError('Ungueltiger Slot oder Mindestanzahl Tage')
    rows = []
    for path in sorted(archive_dir.glob(f'????-??-??/{slot}.json')):
        if path.parent.name not in actuals:
            continue
        if actuals[path.parent.name]['status'] == 'provisional' and not include_provisional:
            continue
        r = archive_record(path, slot)
        observed = actuals[r['date']]
        r['actual_ac_kwh'] = observed['ac_kwh']
        r['actual_status'] = observed['status']
        if 'source_status' in observed:
            r['actual_source_status'] = observed['source_status']
            r['actual_observed_at_utc'] = observed.get('observed_at_utc')
        for i in range(1, 5):
            key = f'wr{i}_kwh'
            if key in observed:
                r[f'actual_{key}'] = observed[key]
        r['error_ac_kwh'] = r['forecast_ac_kwh'] - r['actual_ac_kwh']
        rows.append(r)
    groups = defaultdict(list)
    for r in rows:
        groups[(r['model_hash'], r['physical_hash'], r['near_id'], r['version'])].append(r)
    summary = []
    for (model, physical, near, version), samples in sorted(groups.items(), key=lambda group: tuple(field or "" for field in group[0])):
        entry = {'model_hash': model, 'physical_hash': physical, 'near_id': near,
                 'version': version, 'slot': slot,
                 'first_day': samples[0]['date'], 'last_day': samples[-1]['date'],
                 'status': 'auswertbar' if len(samples) >= min_days else 'zu_wenige_tage',
                 'ac': score(samples)}
        entry['inverters'] = {}
        for i in range(1, 5):
            wr = f'wr{i}_'
            matched = [r for r in samples if f'actual_{wr}kwh' in r and f'forecast_{wr}kwh' in r]
            if matched:
                entry['inverters'][f'wr{i}'] = score(matched, wr)
        summary.append(entry)
    return rows, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--actual', type=Path, required=True, help='CSV: date,ac_kwh[,wr1_kwh,...] ODER SolarEdge-Kiosk-Archiv (.json)')
    p.add_argument('--archive', type=Path, default=Path(__file__).resolve().parents[1]/'prognosen')
    p.add_argument('--slot', choices=['06', '18'], default='06')
    p.add_argument('--min-days', type=int, default=5)
    p.add_argument('--include-provisional', action='store_true', help='nur Sensitivitaetsanalyse; nicht fuer Freigaben')
    p.add_argument('--output', type=Path, default=Path('ac_validierung.json'))
    args = p.parse_args()
    rows, summary = evaluate(args.archive, observations(args.actual), args.slot, args.min_days, args.include_provisional)
    result = {'source': 'original_archived_forecasts_only', 'requires_optimizers': False,
              'total_matched_days': len(rows), 'min_days_per_model': args.min_days,
              'includes_provisional': args.include_provisional,
              'groups': summary, 'daily': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    for group in summary:
        ac = group['ac']
        print(f"{group['version']} {group['first_day']}..{group['last_day']} "
              f"n={ac['n']}, MAE={ac['mae_kwh']:.2f} kWh, "
              f"Bias={ac['bias_kwh']:+.2f} kWh, Status={group['status']}")
    print(f'{len(rows)} AC-Messtage abgeglichen; Bericht: {args.output}')

if __name__ == '__main__':
    main()
