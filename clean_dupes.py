import urllib.request, json, os, urllib.parse

url = f"{os.environ.get('SUPABASE_URL')}/rest/v1/frota_metricas?select=id,horario,regiao,subpraca"
headers = {
    'apikey': os.environ.get('SUPABASE_KEY'), 
    'Authorization': 'Bearer ' + os.environ.get('SUPABASE_KEY')
}
req = urllib.request.Request(url, headers=headers)
data = json.loads(urllib.request.urlopen(req).read().decode())

seen = set()
to_delete = []
for d in data:
    key = (d['horario'], d['regiao'], d['subpraca'])
    if key in seen:
        to_delete.append(d['id'])
    else:
        seen.add(key)

print(f"Found {len(to_delete)} duplicates")
for id in to_delete:
    del_req = urllib.request.Request(f"{os.environ.get('SUPABASE_URL')}/rest/v1/frota_metricas?id=eq.{id}", headers=headers, method="DELETE")
    try:
        urllib.request.urlopen(del_req)
    except:
        pass
print("Done")
