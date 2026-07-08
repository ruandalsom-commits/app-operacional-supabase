import os
import requests
from datetime import datetime

SUPABASE_URL = "https://tgqjyyidogqxioqovhav.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRncWp5eWlkb2dxeGlvcW92aGF2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3Nzg4NjQsImV4cCI6MjA5NTM1NDg2NH0.Hprv50c9SB4aZXiQkWm49nutkN-Gde1Ve0OJR7mwTuk"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

url = f"{SUPABASE_URL}/rest/v1/frota_pedidos_heatmap?select=origin_lat,origin_lng,created_at"

response = requests.get(url, headers=headers)
print("Status Code:", response.status_code)
data = response.json()
print("Number of records matched:", len(data))
if len(data) > 0:
    print("First record:", data[0])
