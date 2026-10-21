"""FDA download diagnostics verify actual ZIP magic, never assume a successful import."""
from urllib.error import HTTPError
import pytest

from scripts.probe_decrs import inspect,probe,DECRS,DECRS_DIRECT_ZIP

class Response:
    def __init__(self,url,data=b'',status=200,content_type='application/zip'):
        self.url=url;self.data=data;self.status=status
        self.headers={'Content-Type':content_type,'Content-Length':str(len(data))}
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def geturl(self):return self.url
    def read(self,n=None):return self.data[:n]

def official(req,timeout=None):
    if req.full_url==DECRS:
        return Response(DECRS,
            b'<a href="https://www.accessdata.fda.gov/cder/drls_reg.zip">Drug establishment annual registration status download file (zip format)</a>',
            content_type='text/html')
    return Response(req.full_url,b'PK\x03\x04__not_a_full_zip',status=206)

def test_probe_reports_header_not_completed_drug_import():
    d=probe(official)
    assert d['landing_page_status']=='parsed'
    assert d['state']=='zip_header_observed'
    assert len(d['tests'])==4
    assert any(x.get('zip_header_verified') for x in d['tests'])
    assert all(x['requested_url']==DECRS_DIRECT_ZIP for x in d['tests'])
    assert 'complete' in d['next_step']

def test_invalid_download_response_not_reported_as_zip():
    def html(req,timeout=None):
        return Response(req.full_url,b'<htm',status=200,content_type='text/html')
    result=inspect(DECRS_DIRECT_ZIP,html)
    assert result['zip_header_verified'] is False
    assert result['http_status']==200

def test_http404_remains_distinct_from_parse_failure():
    def broken(req,timeout=None):
        if req.full_url==DECRS:return Response(DECRS,b'<title>No Link</title>')
        raise HTTPError(req.full_url,404,'Not Found',None,None)
    d=probe(broken)
    assert d['state']=='zip_not_confirmed'
    assert d['landing_page_status']=='unavailable_using_documented_direct_link'
    assert all(item['http_status']==404 for item in d['tests'])

def test_probe_disallows_other_network_hosts():
    with pytest.raises(ValueError,match='official HTTPS FDA hosts'):
        inspect('https://example.net/download.zip',official)
    with pytest.raises(ValueError,match='official HTTPS FDA hosts'):
        inspect('http://www.accessdata.fda.gov/cder/drls_reg.zip',official)
