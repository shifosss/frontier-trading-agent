import json, pathlib, urllib.request, urllib.error
p=pathlib.Path('engines/qualification/evidence')
snapshots=pathlib.Path('.qualification/lean-source-inspection')
snapshots.mkdir(parents=True,exist_ok=True)
d=json.load(urllib.request.urlopen('https://pypi.org/pypi/nautilus_trader/1.231.0/json'))
(p/'pypi-identity.json').write_text(json.dumps({'source':'https://pypi.org/pypi/nautilus_trader/1.231.0/json','version':d['info']['version'],'requires_python':d['info']['requires_python'],'project_urls':d['info']['project_urls'],'license':d['info'].get('license'),'windows_cp313_files':[x for x in d['urls'] if 'cp313-cp313-win_amd64' in x['filename']]},indent=2))
sha=json.loads((p/'lean-identity.json').read_text())['commit']
base='https://raw.githubusercontent.com/QuantConnect/Lean/'+sha+'/'
paths=['Launcher/QuantConnect.Lean.Launcher.csproj','LICENSE','Launcher/config.json','Common/Market.cs','Common/Securities/SecurityPortfolioManager.cs','Common/Securities/Equity/EquityExchange.cs','Data/market-hours/market-hours-database.json','Data/symbol-properties/symbol-properties-database.csv','Common/Securities/DefaultBrokerageModel.cs','README.md']
for path in paths:
    try:
        raw=urllib.request.urlopen(base+path).read()
        (snapshots/('lean-'+path.replace('/','_'))).write_bytes(raw)
        print(path,len(raw))
    except urllib.error.HTTPError as e: print(path,e.code)
