import tempfile,unittest
from pathlib import Path
from scripts.lane_b_epa.rmp_public import import_public
from scripts.lane_b_epa.rmp_lookup import lookup,status,InvalidRMPIndex
class PublicRMPIndexTests(unittest.TestCase):
    def test_deterministic_raw_frs_rmp_order(self):
        def source(reverse):
            def fetch(p):
                if "returnCountOnly" in p:return {"count":3}
                if "returnIdsOnly" in p:return {"objectIds":[3,1,2]}
                values=[int(v) for v in p["objectIds"].split(",")]
                if reverse:values=list(reversed(values))
                return {"features":[{"attributes":{"OBJECTID":v,"REGISTRY_ID":str(v),"PGM_SYS_ID":"RMP"+str(v),
                            "STATE_CODE":"ME","LATITUDE83":44,"LONGITUDE83":-69}} for v in values]}
            return fetch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            a=import_public(root/"a",fetch=source(False),page_size=3)
            b=import_public(root/"b",fetch=source(True),page_size=3)
            self.assertEqual(a["raw_jsonl_sha256"],b["raw_jsonl_sha256"])
            self.assertEqual(a["index_sha256"],b["index_sha256"])
    def test_readonly_public_program_id_lookups_and_verification(self):
        def fake(p):
            if "returnCountOnly" in p:return {"count":2}
            if "returnIdsOnly" in p:return {"objectIds":[1,2]}
            return {"features":[{"attributes":{"OBJECTID":i,"REGISTRY_ID":"FRS001","PGM_SYS_ID":str(i),
                "STATE_CODE":"TX","ACTIVE_STATUS":"Active","LATITUDE83":33.4,"LONGITUDE83":-95.2},
                "geometry":{"x":-95.2,"y":33.4}} for i in map(int,p["objectIds"].split(","))]}
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d)/"public"
            m=import_public(directory,fetch=fake)
            self.assertEqual(m["distinct_program_ids"],2)
            self.assertEqual(m["distinct_registry_ids"],1)
            self.assertEqual(m["state_counts"]["TX"],2)
            result=lookup(directory,"1")
            self.assertEqual(result["observations_available"],1)
            self.assertEqual(result["records"][0]["registry_id"],"FRS001")
            self.assertEqual(result["records"][0]["location_verification"],"NOT_REVIEWED")
            self.assertEqual(status(directory)["index_state"],"INDEXED_NOT_DEPLOYED")
            with self.assertRaises(ValueError):lookup(directory,"1' OR 1=1 --",limit=1000)
            with (directory/"rmp_frs_public.raw.jsonl").open("ab") as f:f.write(b"tamper")
            with self.assertRaises(InvalidRMPIndex):status(directory)
if __name__=="__main__":unittest.main()
