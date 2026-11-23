#!/usr/bin/env python3
"""Compare the archived PV forecast vintages with locally recorded SolarEdge totals."""
import argparse
import json
import math
from datetime import timedelta
from itertools import combinations
from pathlib import Path
from statistics import mean, median

from archiviere_wettervergleich import DATA, FIRST_DAY, LAST_DAY, LOCAL, MODELS, forecast_window, parse_timestamp

IDS = tuple(MODELS)
MIXES = {
    'mean:' + '+'.join(models): models
    for count in range(2, len(IDS) + 1)
    for models in combinations(IDS, count)
}


def score(rows, key):
    errors = [row['forecasts'][key] - row['actualKWh'] for row in rows]
    return {'days': len(errors), 'MAE': mean(map(abs, errors)),
            'RMSE': math.sqrt(mean(e * e for e in errors)), 'bias': mean(errors)} if errors else None


def predicted_regime(indicators):
    clouds = median(indicators[key]['meanCloudCoverPct'] for key in IDS)
    beam = median(indicators[key]['horizontalBeamShare'] for key in IDS)
    if clouds >= 80 and beam <= .15:
        return 'overcastForecast'
    if beam >= .35:
        return 'substantialDirectForecast'
    return 'otherForecast'


def read_archive(day, slot, archive):
    capture = day - timedelta(days=slot == '18')
    path = archive / capture.isoformat() / f'wettervergleich-{slot}.json'
    if not path.exists():
        return None
    obj = json.loads(path.read_bytes())
    observed = parse_timestamp(obj['capturedAtUtc']).astimezone(LOCAL)
    if (obj['schema'] != 1 or obj['targetDay'] != day.isoformat() or obj['slot'] != slot
            or forecast_window(slot, observed) != (capture, day)):
        raise ValueError(f'Archivstand passt nicht zum Zieltag: {path}')
    return obj


def snow_check(days):
    outcomes = {
        'hit': [], 'miss': [], 'falseAlarm': [], 'correctNoSnow': [],
        'warningWithoutObservation': [], 'unknownObservation': [], 'unavailableForecast': [],
    }
    for row in days:
        forecast, observed = row['snowForecast'], row['snowObserved']
        if forecast is None:
            result = 'unavailableForecast'
        elif observed is None:
            result = 'warningWithoutObservation' if forecast else 'unknownObservation'
        elif observed:
            result = 'hit' if forecast else 'miss'
        else:
            result = 'falseAlarm' if forecast else 'correctNoSnow'
        outcomes[result].append(row['day'])
    return outcomes


def summarize(ledger, archive=DATA):
    actuals = {row['day']: row for row in ledger['dailyEnergy']}
    conditions = ledger.get('plantObservations', [])
    snow_days = {row['day'] for row in conditions if row.get('condition') == 'snow_on_modules'}
    clear_days = {row['day'] for row in conditions if row.get('condition') == 'no_snow_on_modules'}
    output = {}
    for slot in ('06', '18'):
        days = []
        for offset in range((LAST_DAY - FIRST_DAY).days + 1):
            day = FIRST_DAY + timedelta(days=offset)
            record = read_archive(day, slot, archive)
            actual = actuals.get(day.isoformat(), {})
            date_key = day.isoformat()
            row = {'day': day.isoformat(), 'actualKWh': actual.get('energyKWh'),
                   'actualStatus': actual.get('status'), 'capturedAtUtc': None,
                   'physicalHash': None, 'forecasts': {}, 'indicators': {},
                   'absoluteErrors': {}, 'nearestSingleModels': [], 'predictedRegime': None,
                   'snowObserved': True if date_key in snow_days else False if date_key in clear_days else None,
                   'snowForecast': None}
            if record:
                row['capturedAtUtc'], row['physicalHash'] = record['capturedAtUtc'], record['physicalHash']
                snow = record.get('snowForecast') or {}
                if snow.get('status') == 'ok':
                    row['snowForecast'] = snow['expectedSnowOnModules']
                for key, model in record['models'].items():
                    if key in MODELS and model['status'] == 'ok':
                        row['forecasts'][key] = model['powerKWh']
                        row['indicators'][key] = model['indicators']
            days.append(row)
        matched = [d for d in days if d['actualKWh'] is not None]
        common = [d for d in matched if d['snowObserved'] is not True and all(key in d['forecasts'] for key in IDS)]
        for row in common:
            row['predictedRegime'] = predicted_regime(row['indicators'])
            row['forecasts'].update({
                key: mean(row['forecasts'][model] for model in models)
                for key, models in MIXES.items()
            })
        for row in matched:
            actual_kwh = row['actualKWh']
            errors = {key: abs(value - actual_kwh) for key, value in row['forecasts'].items()}
            available_models = [key for key in IDS if key in errors]
            if available_models and row['snowObserved'] is not True:
                smallest = min(errors[key] for key in available_models)
                row['nearestSingleModels'] = [
                    key for key in available_models if math.isclose(errors[key], smallest, abs_tol=1e-9)
                ]
            row['absoluteErrors'] = errors
        regimes = {
            name: [d for d in common if d['predictedRegime'] == name]
            for name in ('overcastForecast', 'substantialDirectForecast', 'otherForecast')
        }
        groups = {'all': common, **regimes,
                  'firstTwoWeeks': [d for d in common if d['day'] < (FIRST_DAY + timedelta(days=14)).isoformat()],
                  'lastWeek': [d for d in common if d['day'] >= (FIRST_DAY + timedelta(days=14)).isoformat()]}
        keys = (*IDS, *MIXES)
        output[slot] = {
            'targetDays': len(days), 'actualDays': len(matched),
            'availablePerModel': {key: sum(key in d['forecasts'] for d in days) for key in IDS},
            'commonDays': [d['day'] for d in common],
            'scores': {name: {key: score(rows, key) for key in keys} for name, rows in groups.items()},
            'snowCheck': snow_check(days),
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
