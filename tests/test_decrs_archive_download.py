"""FDA public ZIP download must work with documented browser-agent fallback."""
import io
import urllib.error
import zipfile
import pytest
from scripts.build_catalog import download_zip,DECRS_DIRECT_ZIP

def test_public_fda_zip_fallback_only_on_official_accessdata_host(monkeypatch):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:
        archive.writestr('drls_reg.txt','Firm Name\tFEI Number\tCountry\nAcme Pharma\t123456789\tUS\n')
    calls=[]
    class Reply(io.BytesIO):
        def geturl(self):return DECRS_DIRECT_ZIP
    def fetch(req,timeout=180):
        calls.append(dict(req.header_items()))
        if len(calls)==1:
            raise urllib.error.HTTPError(req.full_url,404,'Not Found',None,None)
        assert 'Mozilla/5.0' in dict(req.header_items())['User-agent']
        return Reply(buffer.getvalue())
    monkeypatch.setattr('scripts.build_catalog.urllib.request.urlopen',fetch)
    path=download_zip(DECRS_DIRECT_ZIP)
    try:
        assert zipfile.is_zipfile(path)
        assert len(calls)==2
    finally:
        path.unlink()
    calls.clear()
    with pytest.raises(urllib.error.HTTPError):
        download_zip('https://download.open.fda.gov/test.zip')
    assert len(calls)==1

def test_drug_zip_fallback_rejects_untrusted_redirect(monkeypatch):
    calls=[]
    class Reply(io.BytesIO):
        def geturl(self):return 'https://invalid.example.org/proxy.zip'
    def fetch(req,timeout=180):
        calls.append(req)
        if len(calls)==1:
            raise urllib.error.HTTPError(req.full_url,404,'Not Found',None,None)
        return Reply(b'PK\x03\x04')
    monkeypatch.setattr('scripts.build_catalog.urllib.request.urlopen',fetch)
    with pytest.raises(ValueError,match='unexpected host'):
        download_zip(DECRS_DIRECT_ZIP)
