import urllib.request, json, os, urllib.parse

url = f"{os.environ.get('SUPABASE_URL')}/rest/v1/frota_metricas?praca=eq.Fortaleza&select=horario,subpraca,trabalhando&order=horario.desc&limit=10"
headers = {
    'apikey': os.environ.get('SUPABASE_KEY'), 
    'Authorization': 'Bearer ' + os.environ.get('SUPABASE_KEY')
}
req = urllib.request.Request(url, headers=headers)
data = json.loads(urllib.request.urlopen(req).read().decode())
print(json.dumps(data, indent=2))
