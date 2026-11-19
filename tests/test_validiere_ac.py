"""AC-Validierung benoetigt keine Modul-, String- oder Optimierermesswerte."""
import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from validiere_ac import observations, archive_record, evaluate

class AcOnlyEvaluation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'prognosen'
        self.csv = self.root / 'ac.csv'

    def snapshot(self, day, pred, model='a', wr=False, physical='p'):
        path = self.repo/day/'06.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        at = datetime.fromisoformat(day+'T06:03:00').replace(tzinfo=ZoneInfo('Europe/Berlin')).isoformat()
        doc = {'day':day,'slot':'06','recordedAt':at,'modelHash':model,'modelVersion':'V1',
               'nearProfileId':'near','centralConfiguration':{'physicalHash':physical},
               'weatherDiagnostics':{'notLive':False},'powerKWh':pred}
        if wr:
            doc.update(inverterConfiguration={'panels':[{'name':'Dach','inverterId':'wr-2'}]},
                       byPanel=[{'name':'Dach','kWh':pred}])
        path.write_text(json.dumps(doc))
        return path

    def actuals(self, rows):
        with self.csv.open('w', newline='') as f:
            w = csv.writer(f); w.writerow(('date','ac_kwh','wr2_kwh'))
            w.writerows(rows)
        return observations(self.csv)

    def test_ac_only_and_optional_wr(self):
        for d,v in [('2026-11-09',10),('2026-11-10',20),('2026-11-11',30),('2026-11-12',40),('2026-11-13',50)]:
            self.snapshot(d,v+2,wr=d=='2026-11-09')
        observed = self.actuals([(f'2026-11-{d:02}',d*10-80,'10' if d==9 else '') for d in range(9,14)])
        rows, groups = evaluate(self.repo,observed, min_days=5)
        self.assertEqual(len(rows),5)
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['status'],'auswertbar')
        self.assertAlmostEqual(groups[0]['ac']['mae_kwh'],2)
        self.assertEqual(groups[0]['inverters']['wr2']['n'],1)

    def test_no_model_mixing(self):
        self.snapshot('2026-11-09', 10, 'a')
        self.snapshot('2026-11-10', 10, 'b')
        actuals = self.actuals([('2026-11-09',9,''),('2026-11-10',10,'')])
        rows, groups = evaluate(self.repo, actuals, min_days=2)
        self.assertEqual(len(groups),2)
        self.assertTrue(all(g['status']=='zu_wenige_tage' for g in groups))

    def test_reject_late_snapshot(self):
        path = self.snapshot('2026-11-09', 10)
        j = json.loads(path.read_text());j['recordedAt']='2026-11-09T12:00:00+01:00';path.write_text(json.dumps(j))
        with self.assertRaisesRegex(ValueError,'keine gueltige'):
            archive_record(path,'06')

    def test_bad_observations_are_rejected(self):
        with self.assertRaises(ValueError):
            self.actuals([('2026-11-09',10,''),('2026-11-09',11,'')])
        with self.assertRaises(ValueError):
            self.actuals([('2026-11-09',-1,'')])

if __name__ == '__main__':
    unittest.main()
