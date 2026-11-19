"""Import historical site-level AC energy from saved SolarEdge kiosk archives.

No module, optimizer, voltage or string telemetry is used. Current-day and
evening-only readings remain provisional even if a calendar day has elapsed.
"""
import json
import math
from datetime import date
from pathlib import Path

STATES = {
    'historical_reported_value': 'reported',
    'final': 'final',
    'final_reported_value': 'final',
    'evening_reported_value_not_final': 'provisional',
    'intraday_provisional': 'provisional',
}


def load_kiosk_ac(path: Path):
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    records = doc.get('dailyEnergy')
    if not isinstance(records, list) or not records:
        raise ValueError('SolarEdge archive must contain nonempty dailyEnergy array')
    output = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('Invalid dailyEnergy record')
        day = date.fromisoformat(record['day']).isoformat()
        if day in output:
            raise ValueError('Duplicate SolarEdge day: ' + day)
        status = STATES.get(record.get('status'))
        if status is None:
            raise ValueError('Unknown SolarEdge energy status on ' + day)
        watt_hours = record.get('energyWh')
        kilowatt_hours = record.get('energyKWh')
        if type(watt_hours) not in (int, float) or not math.isfinite(watt_hours) or watt_hours < 0:
            raise ValueError('Invalid SolarEdge Wh on ' + day)
        if type(kilowatt_hours) not in (int, float) or not math.isfinite(kilowatt_hours) or kilowatt_hours < 0:
            raise ValueError('Invalid SolarEdge kWh on ' + day)
        if abs(watt_hours / 1000 - kilowatt_hours) > 0.00051:
            raise ValueError('Inconsistent Wh/kWh on ' + day)
        output[day] = {'ac_kwh': kilowatt_hours, 'status': status,
                       'source_status': record['status'],
                       'observed_at_utc': record.get('observedAtUtc')}
    return output
