import urllib.request, json, os, urllib.parse
url = f"{os.environ.get('SUPABASE_URL')}/rest/v1/frota_metricas?praca=eq.Fortaleza&select=horario,subpraca,trabalhando"
req = urllib.request.Request(url, headers={'apikey': os.environ.get('SUPABASE_KEY'), 'Authorization': 'Bearer ' + os.environ.get('SUPABASE_KEY')})
data = json.loads(urllib.request.urlopen(req).read().decode())
res = [d for d in data if '15:' in d['horario']]
print(json.dumps(res, indent=2))
