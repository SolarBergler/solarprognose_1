"""Regression against prior relative geometry, at a synthetic test origin."""
import copy,json,math,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from erstelle_modullayout import correct_existing_house_right

class HouseRightPlacementTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((ROOT/'anlagenkonfiguration.json').read_text())
        self.old=json.loads((ROOT/'tests/fixtures/house-right-revision-4.json').read_text())
        # The baseline deliberately contains no real-world coordinates. Restore
        # its measured relative metre offsets around the synthetic origin 0, 0.
        self.old.pop('fixtureNote')
        self.old['referencePoint'].update(latitude=0.0,longitude=0.0)
        a=6378137;e2=.00669437999014
        def coordinates(item):
            item['latitude']=math.degrees(item.pop('north_m')/(a*(1-e2)))
            item['longitude']=math.degrees(item.pop('east_m')/a)
        for module in self.old['geo']['modulePositions']:coordinates(module)
        coordinates(self.old['geo'])
        self.index=next(i for i,p in enumerate(self.config['panels']) if p['name']=='Haus rechts')
        self.config['panels'][self.index]=copy.deepcopy(self.old)

    def test_whole_field_moves_two_rows_with_source_gps_and_window_gap_preserved(self):
        before=copy.deepcopy(self.config)
        self.assertTrue(correct_existing_house_right(self.config))
        after=self.config['panels'][self.index]
        self.assertEqual(after['layoutSurvey']['registrationCorrection']['sourceReferencePoint'],self.old['referencePoint'])
        self.assertNotEqual(after['referencePoint']['latitude'],self.old['referencePoint']['latitude'])
        self.assertEqual(after['moduleGroups'],self.old['moduleGroups'])
        self.assertEqual(after['inverterId'],'wr-1')
        for i,p in enumerate(before['panels']):
            if i!=self.index:self.assertEqual(self.config['panels'][i],p)
        for k,v in before.items():
            if k!='panels':self.assertEqual(self.config[k],v)
        old={m['id']:m for m in self.old['geo']['modulePositions']}
        self.assertEqual(len(after['geo']['modulePositions']),19)
        self.assertEqual({m['id'] for m in after['geo']['modulePositions']},set(old))
        self.assertEqual(sum(m['wp'] for m in after['geo']['modulePositions']),6275)
        lat=math.radians(self.old['referencePoint']['latitude']);a=6378137;e2=.00669437999014
        north_radius=a*(1-e2)/(1-e2*math.sin(lat)**2)**1.5
        east_radius=a/math.sqrt(1-e2*math.sin(lat)**2)*math.cos(lat)
        for m in after['geo']['modulePositions']:
            previous=old[m['id']]
            for key in ['id','wp','groupIndex','width_m','depth_m','roofX_m','roofY_m']:
                self.assertEqual(m[key],previous[key])
            east=math.radians(m['longitude']-previous['longitude'])*east_radius
            north=math.radians(m['latitude']-previous['latitude'])*north_radius
            self.assertAlmostEqual(math.hypot(east,north),1.6244246274,places=5)
            # The two nearby geodetic tangent planes differ far below 1 mm.
            self.assertAlmostEqual(math.degrees(math.atan2(east,north))%360,165,places=3)
            self.assertFalse(abs(m['roofX_m'])<m['width_m']/2 and abs(m['roofY_m'])<m['depth_m']/2,
                             'Der Fensterbezug darf nicht in einem Modul liegen')

    def test_reapplying_correction_cannot_accumulate_another_two_rows(self):
        self.assertTrue(correct_existing_house_right(self.config))
        once=copy.deepcopy(self.config)
        self.assertFalse(correct_existing_house_right(self.config))
        self.assertEqual(self.config,once)

if __name__=='__main__':unittest.main()
