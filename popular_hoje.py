import os
import time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

os.environ["SUPABASE_URL"] = "https://tgqjyyidogqxioqovhav.supabase.co"
os.environ["SUPABASE_KEY"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRncWp5eWlkb2dxeGlvcW92aGF2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3Nzg4NjQsImV4cCI6MjA5NTM1NDg2NH0.Hprv50c9SB4aZXiQkWm49nutkN-Gde1Ve0OJR7mwTuk"

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'api'))
from pedidos import CONTAS, Sessao, extrair_campos_heatmap

def processar_tudo():
    minutos = 1440 # 24 horas
    now_utc = datetime.now(timezone.utc)
    inicio_utc = (now_utc - timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    fim_utc    = now_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    todas_contas_ativas = [c for c in CONTAS if c.get("ativo", True)]
    sessoes = [Sessao(c) for c in todas_contas_ativas]
    
    todos_registros = []

    for sessao in sessoes:
        print(f"Buscando para {sessao.email} de {inicio_utc} a {fim_utc}")
        try:
            sessao.renovar_jwt()
            pedidos = sessao.extrair_todos_pedidos(inicio_utc, fim_utc)
            print(f"  Encontrados {len(pedidos)} pedidos.")
            
            def processar_pedido(r):
                order_id = r.get("orderId")
                if not order_id: return None
                try:
                    detalhe = sessao.buscar_detalhe(order_id)
                    return extrair_campos_heatmap(detalhe)
                except Exception as e:
                    return None

            with ThreadPoolExecutor(max_workers=16) as ex:
                futs = [ex.submit(processar_pedido, r) for r in pedidos]
                for f in as_completed(futs):
                    res = f.result()
                    if res: todos_registros.append(res)
        except Exception as e:
            print(f"Erro ao processar conta {sessao.email}: {e}")
            continue
                
    # Salvar em lotes no supabase
    if todos_registros:
        print(f"Enviando {len(todos_registros)} registros para o Supabase...")
        lote_tamanho = 100
        supa_url = os.environ["SUPABASE_URL"].rstrip('/')
        url = f"{supa_url}/rest/v1/frota_pedidos_heatmap"
        headers = {
            "apikey": os.environ["SUPABASE_KEY"], 
            "Authorization": f"Bearer {os.environ['SUPABASE_KEY']}", 
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        import urllib.request
        for i in range(0, len(todos_registros), lote_tamanho):
            lote = todos_registros[i:i+lote_tamanho]
            try:
                body = json.dumps(lote).encode("utf-8")
                req = urllib.request.Request(url, headers=headers, data=body, method="POST")
                with urllib.request.urlopen(req) as resp:
                    pass
                print(f"  Lote {i} enviado.")
            except Exception as e:
                print(f"  Erro ao enviar lote {i}: {e}")
                
    print("Concluido!")

if __name__ == "__main__":
    processar_tudo()
