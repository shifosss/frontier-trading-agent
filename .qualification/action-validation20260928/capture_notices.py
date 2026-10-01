"""Capture only public primary notices already discovered for 24 frozen cases."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from html.parser import HTMLParser
import hashlib, json, httpx

ROOT = Path(__file__).resolve().parent
NOTICES = [
("DHR", "2016-07-05", "https://investors.danaher.com/2016-07-02-Danaher-Corporation-Completes-Separation-of-Fortive-Corporation"),
("LINK", "2016-04-04", "https://www.sec.gov/Archives/edgar/data/828146/000155837016004899/link-20160620xdef14a.htm"),
("MRBK", "2023-03-21", "https://investor.meridianbanker.com/documents/meridian-corporation-declares-two-for-one-stock-split/"),
("IP", "2021-10-01", "https://www.sec.gov/Archives/edgar/data/51434/000005143422000040/ip-20220630.htm"),
("OLOX", "2023-09-28", "https://www.sec.gov/Archives/edgar/data/1023994/000121390026073749/ea0295463-10k_olenox.htm"),
("NTES", "2020-10-02", "https://ir.netease.com/node/12531"),
("EVO", "2021-10-20", "https://www.sec.gov/Archives/edgar/data/1412558/000110465922049929/evo-20211231x20f.htm"),
("CZFS", "2024-06-14", "https://www.nasdaq.com/press-release/citizens-financial-services-inc-reports-unaudited-second-quarter-2024-financial"),
("ODFL", "2024-03-28", "https://www.sec.gov/Archives/edgar/data/878927/000095017024040017/odfl-20240402.htm"),
("DIT", "2026-03-23", "https://www.sec.gov/Archives/edgar/data/928465/000110465926045515/dit-20260331x10q.htm"),
("BRAI", "2026-04-29", "https://www.sec.gov/Archives/edgar/data/2076975/000149315226016061/ex99-1.htm"),
("WMT", "2024-02-26", "https://corporate.walmart.com/news/2024/01/30/walmart-announces-3-for-1-stock-split"),
("TOPS", "2017-10-06", "https://www.sec.gov/Archives/edgar/data/1296484/000091957419002626/d8214366_20-f.htm"),
("CRVO", "2023-08-17", "https://www.sec.gov/Archives/edgar/data/1053691/000143774923024064/ex_562007.htm"),
("ENOV", "2022-04-05", "https://ir.enovis.com/news-releases/news-release-details/enovis-formerly-colfax-completes-spin-esab-corporation"),
("CYPH", "2023-06-21", "https://www.sec.gov/Archives/edgar/data/1509745/000110465923072982/tm2319198d1_ex99-1.htm"),
("CYPH-mapping", "2023-06-21", "https://www.sec.gov/Archives/edgar/data/1509745/000110465925109820/tm2530735d1_8k.htm"),
("NUWE", "2022-12-12", "https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-421"),
("QXL", "2022-09-06_2025-03-14", "https://www.sec.gov/Archives/edgar/data/797542/000149315226037811/form10-q.htm"),
("QXL-mapping", "2022-09-06_2025-03-14", "https://www.globenewswire.com/news-release/2026/04/30/3284966/0/en/after-successful-acquisition-quantum-x-labs-commences-trading-under-new-name-and-new-nasdaq-ticker-symbol-qxl-today.html"),
("ALM", "2025-07-07", "https://www.sec.gov/Archives/edgar/data/1670061/000149315226037264/ex99-3.htm"),
("HON", "2026-06-29", "https://www.sec.gov/Archives/edgar/data/773840/000077384026000084/exhibit991-pressrelease629.htm"),
("WHLR", "2024-11-19", "https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2024-561"),
("STKH", "2025-04-28", "https://www.sec.gov/Archives/edgar/data/1828098/000121390026050174/ea0287480-20f_steakholder.htm"),
("WOK", "2025-12-29", "https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2025-708"),
]
class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.skip+=1
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        if tag in ('p','div','tr','br','li','h1','h2','h3'): self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)
def dump(path, value):
    path.write_text(json.dumps(value,indent=2),encoding='utf-8')
def capture(item):
    symbol, session, url=item
    stem=f"notice-{symbol}-{session}"
    meta_path=ROOT/(stem+'.capture.json')
    assert not meta_path.exists(), 'Attempts immutable'
    meta=dict(symbol=symbol,effective_sessions=session,url=url,method='GET',started_at=datetime.now(timezone.utc).isoformat(),status='request_started')
    dump(meta_path,meta)
    try:
        with httpx.Client(timeout=35,follow_redirects=True,headers={'User-Agent':'Mozilla/5.0 (compatible; local source-validation research)','Accept':'text/html,application/xhtml+xml'}) as client:
            response=client.get(url)
        raw=response.content; digest=hashlib.sha256(raw).hexdigest()
        filename=stem+'.'+digest+'.raw.html'; (ROOT/filename).write_bytes(raw)
        meta.update(status='response_retained',status_code=response.status_code,final_url=str(response.url),redirects=[dict(status=r.status_code,url=str(r.url)) for r in response.history],sha256=digest,raw_file=filename,bytes=len(raw),captured_at=datetime.now(timezone.utc).isoformat())
        if response.status_code==200:
            parser=Text(); parser.feed(response.text)
            text='\n'.join(' '.join(line.split()) for line in ''.join(parser.parts).splitlines() if line.strip())
            (ROOT/(stem+'.text.txt')).write_text(text,encoding='utf-8')
            meta['text_file']=stem+'.text.txt'
        dump(meta_path,meta)
        return symbol,response.status_code,len(raw)
    except httpx.HTTPError as exc:
        meta.update(status='failed',error_type=type(exc).__name__,completed_at=datetime.now(timezone.utc).isoformat());dump(meta_path,meta)
        return symbol,type(exc).__name__
if __name__=='__main__':
    dump(ROOT/'notice-request-manifest.json',[dict(symbol=s,effective_sessions=d,url=u) for s,d,u in NOTICES])
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(capture,NOTICES): print(result,flush=True)

