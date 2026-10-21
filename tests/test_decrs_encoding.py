"""FDA DECRS may contain Windows-1252 bytes after long ASCII-only prefixes."""
import json
import zipfile
from facilityrisk.registry_catalog import parse_drug_zip,make_catalog,validate_catalog

def test_late_non_utf8_bytes_do_not_break_full_official_text_archive(tmp_path):
    data=(' FEI_NUMBER\tDUNS_NUMBER\tFIRM_NAME\tADDRESS\tEXPIRATION_DATE\tOPERATIONS\t'
          'ESTABLISHMENT_CONTACT_EMAIL\tREGISTRANT_NAME\tEXCLUSION_FLAG\r\n')
    # More than the old 64KB preview of ASCII source rows.
    data+=''.join(f'{1000000000+i}\t\tMFG TEST {i}\tSTREET {i}\t2026-12-31\tMANUFACTURE\tcontact@example.invalid\tREGISTRANT\t\r\n'
                  for i in range(1700))
    data+='9999999999\t123456789\tPHARMACIE QUÉBEC\t3 RUE\t2026-12-31\tMANUFACTURE\tprivate@example.invalid\tFIRM\t\r\n'
    path=tmp_path/'official.zip'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('drls_reg.txt',data.encode('cp1252'))
        z.writestr('drls_reg.xls',b'not a source parser field')
    rows=list(parse_drug_zip(path))
    assert len(rows)==1701
    tail=next(r for r in rows if r['fei']=='9999999999')
    assert tail['name']=='PHARMACIE QUÉBEC'
    assert tail['registration_number']=='123456789'
    assert tail['expiry_year']=='2026-12-31'
    assert 'private@example.invalid' not in json.dumps(rows)
    catalog=make_catalog(rows,{'fda_drug':{'status':'imported'}})
    assert catalog['summary']['by_sector']['Pharmaceutical']==1701
    validate_catalog(catalog)

def test_utf8_archive_with_non_ascii_remains_utf8(tmp_path):
    value='Málaga Manufacturing'
    raw='FIRM_NAME\tFEI_NUMBER\tDUNS_NUMBER\tADDRESS\tOPERATIONS\n'+value+'\t1234567890\t\tAvenue 1\tManufacture\n'
    path=tmp_path/'utf8.zip'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('sites.txt',raw.encode('utf-8-sig'))
    rows=list(parse_drug_zip(path))
    assert len(rows)==1
    assert rows[0]['name']==value
