import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
import imaplib
import email
import re
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler

# ============================================================
# CONFIGURACOES
# ============================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

IMAP_SERVIDOR = "email-ssl.com.br"
IMAP_PORTA    = 993

CONTAS = [
    {
        "email":       "ruan.dalsom@masterdeliveryexpress.com.br",
        "senha":       "Ruankz100%",
        "email_senha": ".#znNtMqwE8fSZw",
        "ativo":       True
    },
    {
        "email":       "ruan.dalsom@crmasterfilial1rj.com.br",
        "senha":       "Ruankz100%",
        "email_senha": ".#znNtMqwE8fSZw",
        "ativo":       True
    },
    {
        "email":       "ruan.dalson@entregoaldeota.com.br",
        "senha":       "Ruankz100%",
        "email_senha": "N2)8T3ecqEP4~]",
        "ativo":       True
    },
]

# URLS
URL_VALIDATE       = "https://api.entregolog.com/logistics-web-bff/operation/users/authentication/validate"
URL_TOKEN          = "https://api.entregolog.com/logistics-web-bff/operation/users/authentication/token"
URL_REFRESH        = "https://api.entregolog.com/logistics-web-bff/operation/users/authentication/token/refresh"
URL_ORDERS         = "https://api.entregolog.com/logistics-web-bff/operation/logistics-operator/orders"
URL_DETALHE_PEDIDO = "https://api.entregolog.com/logistics-web-bff/operation/logistics-operator/orders/{order_id}"

HEADERS_BASE = {
    "accept":                 "application/json, text/plain, */*",
    "accept-language":        "pt",
    "origin":                 "https://franqueado.entregolog.com",
    "referer":                "https://franqueado.entregolog.com/",
    "user-agent":             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "x-cookie-login":         "true",
    "x-country":              "BR",
    "x-ifood-logistics-auth": "true",
    "x-timezone":             "America/Sao_Paulo",
}

PAUSA_ENTRE_DETALHES = 0.15
LIMITE = 50

class Sessao:
    def __init__(self, conta):
        self.email        = conta["email"]
        self.senha        = conta["senha"]
        self.email_senha  = conta.get("email_senha", "")
        self.cookie_jar   = http.cookiejar.CookieJar()
        self.opener       = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.logs         = []

    def log(self, msg):
        self.logs.append(msg)

    def buscar_codigo_email(self, tentativas=6, intervalo=2):
        momento = datetime.now(timezone.utc)
        for tentativa in range(tentativas):
            try:
                imap = imaplib.IMAP4_SSL(IMAP_SERVIDOR, IMAP_PORTA)
                imap.login(self.email, self.email_senha)
                imap.select("INBOX")
                _, msgs = imap.search(None, '(UNSEEN FROM "naoresponda@entregolog.com")')
                if msgs[0]:
                    ids = msgs[0].split()
                    for uid in reversed(ids):
                        _, data = imap.fetch(uid, "(RFC822)")
                        msg = email.message_from_bytes(data[0][1])
                        
                        corpo = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    corpo = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                    break
                        else:
                            corpo = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                        match = re.search(r'\b(\d{6})\b', corpo)
                        if match:
                            codigo = match.group(1)
                            imap.store(uid, '+FLAGS', '\\Seen')
                            imap.logout()
                            self.log("Codigo encontrado no IMAP")
                            return codigo
                imap.logout()
            except Exception as e:
                self.log(f"Erro IMAP na tentativa {tentativa}: {str(e)}")
            time.sleep(intervalo)
        self.log("Codigo nao encontrado apos todas as tentativas")
        raise Exception("Codigo nao encontrado")

    def carregar_jwt(self):
        if hasattr(self, 'jwt_local') and self.jwt_local:
            return self.jwt_local
            
        supa_url = SUPABASE_URL.rstrip('/') if SUPABASE_URL else ""
        if not supa_url or not SUPABASE_KEY: return None
        try:
            url = f"{supa_url}/rest/v1/frota_tokens?select=jwt&email=eq.{urllib.parse.quote(self.email)}"
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and len(data) > 0:
                    self.jwt_local = data[-1].get("jwt")
                    return self.jwt_local
                self.log("JWT nao encontrado no banco para este email")
        except Exception as e:
            self.log(f"Erro carregar JWT: {str(e)}")
        return None

    def salvar_jwt(self, jwt):
        self.jwt_local = jwt
        supa_url = SUPABASE_URL.rstrip('/') if SUPABASE_URL else ""
        if not supa_url or not SUPABASE_KEY: return
        try:
            url = f"{supa_url}/rest/v1/frota_tokens"
            headers = {
                "apikey": SUPABASE_KEY, 
                "Authorization": f"Bearer {SUPABASE_KEY}", 
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates"
            }
            body = json.dumps({"email": self.email, "jwt": jwt}).encode("utf-8")
            req = urllib.request.Request(url, headers=headers, data=body, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                pass
            self.log("JWT salvo no banco (UPSERT)")
        except Exception as e:
            self.log(f"Erro salvar JWT: {str(e)}")

    def get_cookie(self, nome):
        for c in self.cookie_jar:
            if c.name == nome:
                return c.value
        return None

    def fazer_request(self, url, headers_extra=None, body=None, method=None):
        jwt = self.carregar_jwt()
        cookie = f"entregolog_jwt={jwt}" if jwt else ""
        h = {**HEADERS_BASE, "cookie": cookie, **(headers_extra or {})}
        req = urllib.request.Request(url, headers=h, data=body)
        if method: req.get_method = lambda: method
        try:
            with self.opener.open(req, timeout=15) as resp:
                raw = resp.read()
                try: return json.loads(raw.decode("utf-8"))
                except: return {}
        except urllib.error.HTTPError as e:
            raise
        except Exception as e:
            raise

    def fazer_request_com_renovacao(self, url, headers_extra=None, body=None, method=None):
        try:
            return self.fazer_request(url, headers_extra=headers_extra, body=body, method=method)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                renovado = self.renovar_jwt()
                if renovado:
                    return self.fazer_request(url, headers_extra=headers_extra, body=body, method=method)
            raise

    def solicitar_codigo(self):
        self.cookie_jar.clear()
        body = json.dumps({"email": self.email, "password": self.senha}).encode("utf-8")
        h = {**HEADERS_BASE, "content-type": "application/json; charset=UTF-8", "cookie": ""}
        req = urllib.request.Request(URL_VALIDATE, headers=h, data=body)
        with self.opener.open(req, timeout=15) as resp:
            resp.read()
        self.log("Solicitado novo codigo de auth")

    def autenticar(self, codigo, jwt_antigo):
        self.cookie_jar.clear()
        body = json.dumps({"email": self.email, "code": codigo}).encode("utf-8")
        h = {**HEADERS_BASE, "content-type": "application/json; charset=UTF-8", "cookie": f"entregolog_jwt={jwt_antigo}" if jwt_antigo else ""}
        req = urllib.request.Request(URL_TOKEN, headers=h, data=body)
        with self.opener.open(req, timeout=15) as resp:
            resp.read()
        jwt_novo = self.get_cookie("entregolog_jwt")
        if jwt_novo:
            self.salvar_jwt(jwt_novo)
            return jwt_novo
        self.log("Novo JWT nao retornado pela API")
        return None

    def renovar_jwt(self):
        try:
            jwt_antigo = self.carregar_jwt()
            self.solicitar_codigo()
            time.sleep(2)
            codigo = self.buscar_codigo_email()
            jwt_novo = self.autenticar(codigo, jwt_antigo)
            if bool(jwt_novo):
                self.log("JWT renovado com sucesso")
                return True
            return False
        except Exception as e:
            self.log(f"Erro em renovar_jwt: {str(e)}")
            return False

    def buscar_pagina_pedidos(self, page, data_inicio_utc, data_fim_utc):
        params = urllib.parse.urlencode({
            "page":            page,
            "size":            LIMITE,
            "states":          "COMPLETED",
            "sort":            "deliveryTimeWindowEnd,desc",
            "createdDateFrom": data_inicio_utc,
            "createdDateTo":   data_fim_utc,
        })
        params += "&states=CANCELLED&states=RETURNED"
        return self.fazer_request_com_renovacao(f"{URL_ORDERS}?{params}")

    def extrair_todos_pedidos(self, data_inicio_utc, data_fim_utc):
        dados     = self.buscar_pagina_pedidos(0, data_inicio_utc, data_fim_utc)
        total     = dados.get("total", 0)
        registros = dados.get("content", [])
        paginas   = (total + LIMITE - 1) // LIMITE

        for p in range(1, paginas):
            pagina = self.buscar_pagina_pedidos(p, data_inicio_utc, data_fim_utc)
            registros.extend(pagina.get("content", []))

        return registros

    def buscar_detalhe(self, order_id):
        url = URL_DETALHE_PEDIDO.format(order_id=order_id)
        return self.fazer_request_com_renovacao(url)

def extrair_campos_heatmap(detalhe):
    origin      = detalhe.get("origin", {}) or {}
    origin_addr = origin.get("address", {}) or {}
    dest        = detalhe.get("destination", {}) or {}
    dest_addr   = dest.get("address", {}) or {}

    return {
        "order_id":        detalhe.get("orderId") or detalhe.get("id"),
        "delivery_code":   detalhe.get("deliveryCode"),
        "order_reference": detalhe.get("orderReference"),
        "region_name":     (detalhe.get("region") or {}).get("name"),
        "sub_region_name": (detalhe.get("subRegion") or {}).get("name"),
        "cluster_name":    (detalhe.get("cluster") or {}).get("name"),
        "state":           (detalhe.get("state") or {}).get("current"),
        "created_at":      detalhe.get("createdAt"),
        "origin_name":     origin.get("name"),
        "origin_lat":      origin_addr.get("latitude"),
        "origin_lng":      origin_addr.get("longitude"),
        "destination_lat": dest_addr.get("latitude"),
        "destination_lng": dest_addr.get("longitude"),
    }

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        cron_secret = os.environ.get('CRON_SECRET')
        if cron_secret and self.headers.get("Authorization") != f"Bearer {cron_secret}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        if not SUPABASE_URL or not SUPABASE_KEY:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Erro: SUPABASE_URL ou SUPABASE_KEY nao configurados.")
            return

        from urllib.parse import urlparse, parse_qs
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)
        minutos = int(query.get('minutos', [15])[0])

        now_utc = datetime.now(timezone.utc)
        inicio_utc = (now_utc - timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        fim_utc    = now_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        todas_contas_ativas = [c for c in CONTAS if c.get("ativo", True)]
        sessoes = [Sessao(c) for c in todas_contas_ativas]
        
        logs_finais = {}
        todos_registros = []
        erros = []

        def processar_sessao(sessao):
            registros_sessao = []
            sessao_erros = []
            
            def processar_pedido(r):
                order_id = r.get("orderId")
                if not order_id: return None
                try:
                    # Removemos o sleep abusivo para caber no limite serverless (15s a 30s)
                    detalhe = sessao.buscar_detalhe(order_id)
                    return extrair_campos_heatmap(detalhe)
                except Exception as e:
                    sessao_erros.append(f"Erro detalhe {order_id}: {str(e)}")
                    return None

            def buscar_e_processar():
                pedidos = sessao.extrair_todos_pedidos(inicio_utc, fim_utc)
                # Aumenta os workers para despachar o mais rapido possivel no Serverless
                with ThreadPoolExecutor(max_workers=8) as ex:
                    futs = [ex.submit(processar_pedido, r) for r in pedidos]
                    for f in as_completed(futs):
                        res = f.result()
                        if res: registros_sessao.append(res)
                        
            try:
                buscar_e_processar()
            except Exception as e:
                sessao_erros.append(f"Erro listar pedidos {sessao.email}: {str(e)}")
                try:
                    if sessao.renovar_jwt():
                        buscar_e_processar()
                except Exception as e_retry:
                    sessao_erros.append(f"Erro retry {sessao.email}: {str(e_retry)}")
                    
            return registros_sessao, sessao_erros, sessao.logs, sessao.email

        # Processar contas em paralelo
        with ThreadPoolExecutor(max_workers=3) as executor:
            futuros = [executor.submit(processar_sessao, s) for s in sessoes]
            for f in as_completed(futuros):
                try:
                    regs, errs, logs, email_conta = f.result()
                    todos_registros.extend(regs)
                    erros.extend(errs)
                    logs_finais[email_conta] = logs
                except Exception as e:
                    erros.append(f"Erro Thread: {str(e)}")
                            
        # UPSERT no Supabase
        if todos_registros:
            try:
                supa_url = SUPABASE_URL.rstrip('/')
                url = f"{supa_url}/rest/v1/frota_pedidos_heatmap"
                headers = {
                    "apikey": SUPABASE_KEY, 
                    "Authorization": f"Bearer {SUPABASE_KEY}", 
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates"
                }
                
                body = json.dumps(todos_registros).encode("utf-8")
                req = urllib.request.Request(url, headers=headers, data=body, method="POST")
                with urllib.request.urlopen(req) as resp:
                    pass
            except Exception as e:
                erros.append(f"Erro ao inserir no Supabase: {str(e)}")

        self.send_response(200)
        self.send_header('Content-type','application/json')
        self.end_headers()
        
        # Limita o tamanho do array de erros e omite logs na saida p/ não estourar payload do Cron
        res = {
            "status": "ok", 
            "inserted_upserted": len(todos_registros), 
            "erros": erros[:5], # no maximo 5 erros reportados no body
            "logs_omitted": True
        }
        self.wfile.write(json.dumps(res).encode('utf-8'))
        return
