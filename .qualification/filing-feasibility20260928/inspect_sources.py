"""Narrow extraction for three frozen inline-XBRL source examples; not an ingestion engine."""
from pathlib import Path
import xml.etree.ElementTree as ET
import re, json, html, hashlib
from decimal import Decimal, InvalidOperation
P=Path(__file__).parent
SELECTED={'us-gaap:NetIncomeLoss','us-gaap:ProfitLoss','us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic','us-gaap:Assets','us-gaap:EarningsPerShareDiluted','dei:TradingSymbol','dei:SecurityExchangeName','dei:Security12bTitle','dei:DocumentFiscalPeriodFocus','dei:DocumentFiscalYearFocus'}
results={}
for name in ['aapl_2020q3','msft_2024q3','f_2024q2']:
    data=(P/'raw'/(name+'_original.bin')).read_bytes(); text=data.decode('utf-8')
    opening=re.search(r'<html\b[^>]*>',text).group(0)
    fragments=[m.group(0) for m in re.finditer(r'<(xbrli:context|xbrli:unit)\b[^>]*>.*?</\1>',text,re.S)]
    # Original HTML contains injected non-XML script markup. Parse only original context/unit fragments.
    root=ET.fromstring(opening+''.join(fragments)+'</html>')
    contexts={e.get('id'):e for e in root.iter() if e.tag.endswith('}context')}
    units={e.get('id'):ET.tostring(e,encoding='unicode') for e in root.iter() if e.tag.endswith('}unit')}
    rows=[]
    pattern=r'<(ix:nonFraction|ix:nonNumeric)\b(?=[^>]*\bname="(?:'+ '|'.join(re.escape(k) for k in sorted(SELECTED)) +r')")([^>]*)>(.*?)</\1>'
    for m in re.finditer(pattern,text,re.S):
        attrs=dict(re.findall(r'(\S+)="([^"]*)"',m.group(2)))
        if attrs.get('name') not in SELECTED: continue
        ctx=contexts[attrs['contextRef']]
        row=dict(attrs,text=html.unescape(re.sub('<[^>]*>','',m.group(3))).strip(),unit_xml=units.get(attrs.get('unitRef')),context_xml=ET.tostring(ctx,encoding='unicode'),context={e.tag.rsplit('}',1)[-1]:e.text for e in ctx.iter() if e.tag.rsplit('}',1)[-1] in ['startDate','endDate','instant','identifier']},dimensions=[dict(e.attrib,value=e.text) for e in ctx.iter() if e.tag.rsplit('}',1)[-1] in ['explicitMember','typedMember']],original_fragment_sha256=hashlib.sha256(m.group(0).encode()).hexdigest())
        if attrs.get('name','').startswith('us-gaap:'):
            try:
                value=Decimal(0) if attrs.get('format')=='ixt:fixed-zero' else Decimal(row['text'].replace(',',''))
                row['numeric_value']=str(value*Decimal(10)**int(attrs.get('scale','0'))*(-1 if attrs.get('sign')=='-' else 1))
            except InvalidOperation:
                row['extraction_error']='unhandled numeric representation; no inferred value'
        rows.append(row)
    results[name]={'source_sha256':hashlib.sha256(data).hexdigest(),'rows':rows}
(P/'fact-context-inspection.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
for name,result in results.items():
    rows=result['rows']
    selected=[r for r in rows if not r['dimensions'] and r['name'] in {'us-gaap:NetIncomeLoss','us-gaap:ProfitLoss','us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic','us-gaap:Assets'}]
    print(name,json.dumps([{'tag':r['name'],'value':r.get('numeric_value'),'context':r['context']} for r in selected]))
