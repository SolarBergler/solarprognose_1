"""AC observations from the archived SolarEdge site energy feed, no optimizers."""
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from solaredge_ac import load_kiosk_ac
from validiere_ac import observations, evaluate

def archive():
    return {'dailyEnergy':[
        {'day':'2026-11-09','energyWh':15596,'energyKWh':15.596,
         'status':'historical_reported_value','observedAtUtc':'2026-11-14T20:06:52Z'},
        {'day':'2026-11-14','energyWh':40528,'energyKWh':40.528,
         'status':'evening_reported_value_not_final'},
        {'day':'2026-11-15','energyWh':43696,'energyKWh':43.696,
         'status':'intraday_provisional'}]}

class SolarEdgeAC(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.file=Path(self.tmp.name)/'solar.json'
        self.save(archive())
    def save(self,data):
        self.file.write_text(json.dumps(data))
    def test_native_archive_statuses(self):
        rows=observations(self.file)
        self.assertEqual(len(rows),3)
        self.assertEqual(rows['2026-11-09']['ac_kwh'],15.596)
        self.assertEqual(rows['2026-11-09']['status'],'reported')
        self.assertEqual(rows['2026-11-14']['status'],'provisional')
        self.assertEqual(rows['2026-11-15']['status'],'provisional')
    def test_all_provisional_days_are_excluded_from_default_scoring(self):
        root=Path(self.tmp.name)/'archive'
        for day,forecast in [('2026-11-09',17),('2026-11-14',50),('2026-11-15',55)]:
            path=root/day/'06.json';path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'day':day,'slot':'06','recordedAt':day+'T05:02:00Z',
                'modelHash':'model','modelVersion':'V1','nearProfileId':'x',
                'centralConfiguration':{'physicalHash':'phys'},
                'weatherDiagnostics':{'notLive':False},'powerKWh':forecast}))
        rows,groups=evaluate(root,observations(self.file),min_days=1)
        self.assertEqual(len(rows),1)
        self.assertEqual(groups[0]['ac']['n'],1)
        self.assertEqual(rows[0]['actual_source_status'],'historical_reported_value')
    def test_duplicate_day_rejected(self):
        d=archive();d['dailyEnergy'].append(dict(d['dailyEnergy'][0]));self.save(d)
        with self.assertRaisesRegex(ValueError,'Duplicate'):load_kiosk_ac(self.file)
    def test_wh_kwh_disagreement_rejected(self):
        d=archive();d['dailyEnergy'][0]['energyWh']=1337;self.save(d)
        with self.assertRaisesRegex(ValueError,'Inconsistent'):load_kiosk_ac(self.file)
    def test_unknown_status_rejected(self):
        d=archive();d['dailyEnergy'][0]['status']='current';self.save(d)
        with self.assertRaisesRegex(ValueError,'Unknown'):load_kiosk_ac(self.file)
    def test_nonphysical_energy_rejected(self):
        d=archive();d['dailyEnergy'][0]['energyWh']=-1000;self.save(d)
        with self.assertRaisesRegex(ValueError,'Invalid'):load_kiosk_ac(self.file)
    def test_missing_daily_energy_rejected(self):
        self.save({})
        with self.assertRaisesRegex(ValueError,'nonempty'):load_kiosk_ac(self.file)

if __name__=='__main__':unittest.main()
