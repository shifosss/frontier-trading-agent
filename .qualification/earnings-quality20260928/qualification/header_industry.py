"""Original same-CIK FILER industry gate; frozen financial/history parsing unchanged."""
from hashlib import sha256
from pathlib import Path
import importlib.util
import re

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
Q_PATH=REPO/'.qualification/earnings-quality20260928/features/cash_backing.py'
Q_SHA256='b8f54a439a3e119be7f93842b04a4b40fc1c5ae718c203a4b929d0d98dce4673'
if sha256(Q_PATH.read_bytes()).hexdigest()!=Q_SHA256:
    raise ValueError('Frozen Q adapter changed')
_spec=importlib.util.spec_from_file_location('frozen_cash_backing_for_industry',Q_PATH)
Q=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(Q)


def _blocks(raw,tag,start,end):
    """Bounded balanced structural tags, with original absolute byte offsets."""
    token=tag.encode();pattern=rb'</?'+token+rb'\b[^>]*>'
    opened=None;out=[]
    for match in re.finditer(pattern,raw[start:end]):
        a,b=start+match.start(),start+match.end();value=match[0]
        if value==b'<'+token+b'>':
            if opened is not None:raise ValueError('nested_'+tag)
            opened=(a,b)
        elif value==b'</'+token+b'>':
            if opened is None:raise ValueError('unmatched_close_'+tag)
            out.append((opened[0],b,opened[1],a));opened=None
        else:raise ValueError('malformed_structural_tag_'+tag)
    if opened is not None:raise ValueError('unclosed_'+tag)
    return out


def _fields(raw,tag,start,end):
    token=tag.encode();out=[]
    for match in re.finditer(rb'<'+token+rb'\b[^>]*>([^\r\n<]*)',raw[start:end]):
        if match[0].split(b'>',1)[0]!=b'<'+token:raise ValueError('malformed_field_'+tag)
        out.append({'value':match[1].strip().decode('ascii'),'span':[start+match.start(),start+match.end()]})
    return out


def _number(fields,tag,width,positive=False):
    if not fields:raise ValueError('missing_'+tag)
    if any(not re.fullmatch(r'[0-9]{1,'+str(width)+'}',f['value']) for f in fields):raise ValueError('malformed_'+tag)
    values={int(f['value']) for f in fields}
    if len(values)!=1:raise ValueError('conflicting_'+tag)
    value=next(iter(values))
    if positive and value==0:raise ValueError('invalid_zero_'+tag)
    return str(value).zfill(width)


def parse_header(raw,cik,accession):
    """Decode only original SGML structure; no source lookup or current-SIC fallback."""
    result={'industry_status':'unavailable','industry_sic':None,'industry_reasons':[],
            'industry_header_sha256':sha256(raw).hexdigest(),'industry_evidence':[],
            'industry_filers':[]}
    def evidence(kind,span):
        a,b=span;fragment=raw[a:b]
        return {'kind':kind,'span':[a,b],'sha256':sha256(fragment).hexdigest(),'raw_text':fragment.decode('utf-8',errors='replace')}
    try:
        if not re.fullmatch(r'[0-9]{10}',cik) or int(cik)==0:raise ValueError('invalid_expected_CIK')
        headers=_blocks(raw,'SEC-HEADER',0,len(raw))
        if len(headers)!=1:raise ValueError('not_exactly_one_SEC_HEADER')
        hs,he,start,end=headers[0];result['industry_evidence'].append(evidence('SEC-HEADER',[hs,he]))
        accessions=_fields(raw,'ACCESSION-NUMBER',start,end)
        if len(accessions)!=1 or accessions[0]['value']!=accession:raise ValueError('original_accession_mismatch_or_ambiguous')
        result['industry_evidence'].append(evidence('ACCESSION-NUMBER',accessions[0]['span']))
        filers=_blocks(raw,'FILER',start,end)
        if not filers:raise ValueError('missing_FILER')
        matches=[]
        for fs,fe,inner_start,inner_end in filers:
            companies=_blocks(raw,'COMPANY-DATA',inner_start,inner_end)
            if len(companies)!=1:raise ValueError('ambiguous_FILER_COMPANY_DATA')
            cs,ce,ds,de=companies[0]
            cik_fields=_fields(raw,'CIK',ds,de);found=_number(cik_fields,'CIK',10,positive=True)
            result['industry_filers'].append({'filer_span':[fs,fe],'company_data_span':[cs,ce],'cik':found,'cik_fields':cik_fields})
            if found==cik:matches.append((fs,fe,cs,ce,ds,de,cik_fields))
        if len(matches)!=1:raise ValueError('unmatched_or_ambiguous_FILER_CIK')
        fs,fe,cs,ce,ds,de,cik_fields=matches[0]
        sic_fields=_fields(raw,'ASSIGNED-SIC',ds,de)
        for kind,span in [('FILER',[fs,fe]),('COMPANY-DATA',[cs,ce])]:result['industry_evidence'].append(evidence(kind,span))
        for kind,fields in [('CIK',cik_fields),('ASSIGNED-SIC',sic_fields)]:
            result['industry_evidence'].extend(evidence(kind,f['span']) for f in fields)
        sic=_number(sic_fields,'ASSIGNED-SIC',4);code=int(sic)
        result['industry_sic']=sic
        allowed=100<=code<=5999 or 7000<=code<=8999
        result['industry_status']='qualified' if allowed else 'excluded'
        if not allowed:result['industry_reasons'].append('sic_outside_declared_ranges')
    except (ValueError,UnicodeError,TypeError) as error:result['industry_reasons'].append(str(error))
    return result


def source_path(source,source_root,repo_root):
    return (Path(repo_root) if source.get('reused') or source['path'].startswith('.qualification/') else Path(source_root))/source['path']


def qualify_header(manifest,source_root,repo_root):
    result={'industry_status':'unavailable','industry_sic':None,'industry_reasons':[],
            'industry_evidence':[],'industry_filers':[]}
    try:
        cik=manifest['issuer']['cik'];accession=manifest['registry_row']['accessionNumber']
        url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-","")}/{accession}.hdr.sgml'
        sources=[s for s in manifest.get('sources',[]) if s.get('url','').endswith('.hdr.sgml')]
        if len(sources)!=1 or sources[0]['url']!=url or sources[0].get('status')!=200:raise ValueError('original_header_source_missing_or_unmatched')
        source=sources[0];path=source_path(source,source_root,repo_root);raw=path.read_bytes()
        if sha256(raw).hexdigest()!=source['sha256']:raise ValueError('original_header_hash_changed')
        result=parse_header(raw,cik,accession)
        result.update(industry_header_source={'path':str(path.resolve()),'url':url,'sha256':source['sha256'],'bytes':len(raw)})
    except (KeyError,ValueError,OSError,TypeError) as error:result['industry_reasons'].append(str(error))
    return result


def enrich_filing(manifest,source_root,repo_root):
    record=Q.enrich_filing(manifest,source_root,repo_root)
    return dict(record,**qualify_header(manifest,source_root,repo_root))


def build_features(records,calendar):
    results=[]
    for original in Q.build_features(records,calendar):
        reasons=[]
        for field in ['joint_feature_status','industry_status']:
            if original.get(field)!='qualified':reasons.append(field+':'+str(original.get(field,'unavailable')))
        results.append(dict(original,strategy_source_status='unavailable' if reasons else 'qualified',strategy_source_reasons=reasons))
    return results
