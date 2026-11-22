#!/usr/bin/env python3
"""Compare the archived PV forecast vintages with locally recorded SolarEdge totals."""
import argparse
import json
import math
from datetime import timedelta
from pathlib import Path
from statistics import mean

from archiviere_wettervergleich import DATA, FIRST_DAY, LAST_DAY, MODELS, forecast_window, parse_timestamp

IDS = tuple(MODELS)
MIX = 'mean-of-three'
RULE = 'mosmix-if-overcast'


def score(rows, key):
    errors = [row['forecasts'][key] - row['actualKWh'] for row in rows]
    return {'days': len(errors), 'MAE': mean(map(abs, errors)),
            'RMSE': math.sqrt(mean(e * e for e in errors)), 'bias': mean(errors)} if errors else None


def overcast(indicators):
    return indicators['meanCloudCoverPct'] >= 80 and indicators['horizontalBeamShare'] <= .15


def read_archive(day, slot, archive):
    capture = day - timedelta(days=slot == '18')
    path = archive / capture.isoformat() / f'wettervergleich-{slot}.json'
    if not path.exists():
        return None
    obj = json.loads(path.read_bytes())
    from archiviere_wettervergleich import LOCAL
    observed = parse_timestamp(obj['capturedAtUtc']).astimezone(LOCAL)
    if (obj['schema'] != 1 or obj['targetDay'] != day.isoformat() or obj['slot'] != slot
            or forecast_window(slot, observed) != (capture, day)):
        raise ValueError(f'Archivstand passt nicht zum Zieltag: {path}')
    return obj


def summarize(ledger, archive=DATA):
    actuals = {row['day']: row for row in ledger['dailyEnergy']}
    output = {}
    for slot in ('06', '18'):
        days = []
        for offset in range((LAST_DAY - FIRST_DAY).days + 1):
            day = FIRST_DAY + timedelta(days=offset)
            record = read_archive(day, slot, archive)
            actual = actuals.get(day.isoformat(), {})
            row = {'day': day.isoformat(), 'actualKWh': actual.get('energyKWh'),
                   'actualStatus': actual.get('status'), 'capturedAtUtc': None,
                   'physicalHash': None, 'forecasts': {}, 'indicators': {}}
            if record:
                row['capturedAtUtc'], row['physicalHash'] = record['capturedAtUtc'], record['physicalHash']
                for key, model in record['models'].items():
                    if model['status'] == 'ok':
                        row['forecasts'][key] = model['powerKWh']
                        row['indicators'][key] = model['indicators']
            days.append(row)
        matched = [d for d in days if d['actualKWh'] is not None]
        common = [d for d in matched if all(key in d['forecasts'] for key in IDS)]
        primary_keys = ('mosmix', 'icon', 'ifs')
        primary = [d for d in matched if all(key in d['forecasts'] for key in primary_keys)]
        for row in primary:
            forecasts = row['forecasts']
            forecasts[MIX] = mean(forecasts[key] for key in primary_keys)
            if 'best-match' in forecasts:
                forecasts[RULE] = forecasts['mosmix' if overcast(row['indicators']['mosmix']) else 'best-match']
        regimes = {
            'overcastForecast': [d for d in common if overcast(d['indicators']['mosmix'])],
            'substantialDirectForecast': [d for d in common if d['indicators']['mosmix']['horizontalBeamShare'] >= .35],
            'otherForecast': [d for d in common if not overcast(d['indicators']['mosmix'])
                              and d['indicators']['mosmix']['horizontalBeamShare'] < .35],
        }
        groups = {'all': common, **regimes,
                  'firstTwoWeeks': [d for d in common if d['day'] < (FIRST_DAY + timedelta(days=14)).isoformat()],
                  'lastWeek': [d for d in common if d['day'] >= (FIRST_DAY + timedelta(days=14)).isoformat()]}
        keys = (*IDS, MIX, RULE)
        output[slot] = {
            'targetDays': len(days), 'actualDays': len(matched),
            'availablePerModel': {key: sum(key in d['forecasts'] for d in days) for key in IDS},
            'commonThreeModels': {key: score(primary, key) for key in (*primary_keys, MIX)},
            'commonWithReference': {name: {key: score(rows, key) for key in keys} for name, rows in groups.items()},
            'dailyValues': days,
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('solar_edge_ledger', type=Path)
    parser.add_argument('--archive', type=Path, default=DATA)
    args = parser.parse_args()
    ledger = json.loads(args.solar_edge_ledger.read_bytes())
    print(json.dumps(summarize(ledger, args.archive), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
