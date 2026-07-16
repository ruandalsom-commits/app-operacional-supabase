import json
import urllib.request
import urllib.parse

SUPABASE_URL = 'https://tgqjyyidogqxioqovhav.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRncWp5eWlkb2dxeGlvcW92aGF2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3Nzg4NjQsImV4cCI6MjA5NTM1NDg2NH0.Hprv50c9SB4aZXiQkWm49nutkN-Gde1Ve0OJR7mwTuk'

url = f"{SUPABASE_URL}/rest/v1/frota_escalas?select=*&data=eq.2026-07-08&limit=1"
headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        print("Success! Got 1 record.")
except Exception as e:
    print(f"Error limit=1: {e}")

url = f"{SUPABASE_URL}/rest/v1/frota_escalas?select=*&data=eq.2026-07-08"
headers['Range'] = "0-999"

try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print(f"Success! Range 0-999 got {len(data)} records.")
except Exception as e:
    print(f"Error Range 0-999: {e}")

headers['Range'] = "3000-3999"
try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print(f"Success! Range 3000-3999 got {len(data)} records.")
except Exception as e:
    print(f"Error Range 3000-3999: {e}")
