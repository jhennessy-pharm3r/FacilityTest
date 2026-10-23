import tempfile,unittest
from pathlib import Path
from scripts.lane_b_epa.rmp_public import import_public
class RMPLayerTests(unittest.TestCase):
    def test_full_id_reconciliation(self):
        calls=[]
        def fake(params):
            calls.append(params)
            if params.get("returnCountOnly"):return {"count":2}
            if params.get("returnIdsOnly"):return {"objectIds":[20,10]}
            return {"features":[{"attributes":{"OBJECTID":int(i),"REGISTRY_ID":"FRS"+i,"PGM_SYS_ID":"RMP"+i,"LATITUDE83":"40","LONGITUDE83":"-74"},"geometry":{"x":-74,"y":40}} for i in params["objectIds"].split(",")]}
        with tempfile.TemporaryDirectory() as d:
            m=import_public(Path(d)/"staged",fetch=fake,page_size=1)
            self.assertEqual(m["indexed_rows"],2)
            self.assertEqual(m["missing_coordinate_pairs"],0)
            self.assertEqual(m["deployment_state"],"NOT_DEPLOYED")
            self.assertEqual(len([c for c in calls if "objectIds" in c]),2)
    def test_incomplete_ids_fails_closed(self):
        def fake(params):
            return {"count":2} if "returnCountOnly" in params else {"objectIds":[1]}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(AssertionError):import_public(Path(d)/"staged",fetch=fake)
if __name__=="__main__":unittest.main()
