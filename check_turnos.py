import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

SUPABASE_URL = 'https://tgqjyyidogqxioqovhav.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRncWp5eWlkb2dxeGlvcW92aGF2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3Nzg4NjQsImV4cCI6MjA5NTM1NDg2NH0.Hprv50c9SB4aZXiQkWm49nutkN-Gde1Ve0OJR7mwTuk'

fuso_br = timezone(timedelta(hours=-3))
data_alvo = datetime.now(fuso_br).strftime("%Y-%m-%d")

url = f"{SUPABASE_URL}/rest/v1/frota_escalas?select=praca,subpraca,turno,modal,logados,slots&data=eq.{data_alvo}&limit=1000"
headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        
        turnos = set([d.get("turno") for d in data])
        print("Turnos encontrados hoje:")
        for t in sorted(list(turnos)):
            print(f"- {t}")
            
except Exception as e:
    import traceback
    traceback.print_exc()
