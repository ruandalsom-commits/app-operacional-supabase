import urllib.request
import json
from datetime import datetime, timezone, timedelta

SUPABASE_URL = 'https://tgqjyyidogqxioqovhav.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRncWp5eWlkb2dxeGlvcW92aGF2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3Nzg4NjQsImV4cCI6MjA5NTM1NDg2NH0.Hprv50c9SB4aZXiQkWm49nutkN-Gde1Ve0OJR7mwTuk'

fuso_br = timezone(timedelta(hours=-3))
ontem = (datetime.now(fuso_br) - timedelta(days=1)).strftime("%Y-%m-%d")

url_count = f"{SUPABASE_URL}/rest/v1/frota_metricas?select=id&horario=like.{ontem}%"
headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Prefer": "count=exact"}

try:
    req = urllib.request.Request(url_count, headers=headers)
    with urllib.request.urlopen(req) as resp:
        content_range = resp.getheader('content-range')
        print(f"Total entries yesterday ({ontem}): {content_range}")
except Exception as e:
    print(f"Erro: {e}")
