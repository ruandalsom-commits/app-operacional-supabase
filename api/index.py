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
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler

# Sem dependencias externas para Vercel

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
        "ativo":       True,
        "regioes": [
            {"nome": "Sao Paulo", "uuid": "3841c245-fac1-40a6-8b8f-8d6876447a6d"},
        ]
    },
    {
        "email":       "ruan.dalsom@crmasterfilial1rj.com.br",
        "senha":       "Ruankz100%",
        "email_senha": ".#znNtMqwE8fSZw",
        "ativo":       True,
        "regioes": [
            {"nome": "Rio - Madureira",    "uuid": "2800ed66-03d2-4877-880a-8de7ad2051cd"},
            {"nome": "Rio - Barra",        "uuid": "30a4c365-0ff0-4db7-8691-82e8470b3820"},
            {"nome": "Rio - Zona Sul",     "uuid": "4506e189-2547-4b77-a711-304f519da4d0"},
            {"nome": "Niteroi",            "uuid": "2721a164-0a92-4106-8aca-d68b6e4de9b3"},
            {"nome": "Rio - Campo Grande", "uuid": "82c43d58-08d5-4e15-9656-d4cf41b67855"},
        ]
    },
    {
        "email":       "ruan.dalson@entregoaldeota.com.br",
        "senha":       "Ruankz100%",
        "email_senha": "N2)8T3ecqEP4~]",
        "ativo":       True,
        "regioes": [
            {"nome": "Fortaleza", "uuid": "5ed2c46b-f439-45f6-a6c1-a4ff03519fdd"},
        ]
    },
]

PREFIXO_DEDICADO = {
    "Sao Paulo":          "SP",
    "Rio - Madureira":    "RJ",
    "Rio - Barra":        "RJ",
    "Rio - Zona Sul":     "RJ",
    "Niteroi":            "RJ",
    "Rio - Campo Grande": "RJ",
    "Fortaleza":          "FOR",
}

# URLS
URL_VALIDATE   = "https://api.entregolog.com/logistics-web-bff/operation/users/authentication/validate"
URL_TOKEN      = "https://api.entregolog.com/logistics-web-bff/operation/users/authentication/token"
URL_REFRESH    = "https://api.entregolog.com/logistics-web-bff/operation/users/authentication/token/refresh"
URL_FROTA      = "https://api.entregolog.com/logistics-web-bff/operation/logistics-operator/position-map/non-federated"
URL_SUBREGIONS = "https://api.entregolog.com/logistics-web-bff/operation/logistics-operator/position-map/filter/sub-regions"
URL_ORIGINS    = "https://api.entregolog.com/logistics-web-bff/operation/logistics-operator/position-map/filter/origins"

HEADERS_BASE = {
    "accept":                 "application/json, text/plain, */*",
    "accept-language":        "pt",
    "origin":                 "https://franqueado.entregolog.com",
    "referer":                "https://franqueado.entregolog.com/",
    "user-agent":             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "x-cookie-login":         "true",
    "x-country":              "BR",
    "x-ifood-logistics-auth": "true",
    "x-timezone":             "America/Sao_Paulo",
}

STATUS_LIST = ["BLOCKED", "WORKING", "OFFLINE", "PAUSED", "AVAILABLE"]

# Supabase configurado via HTTP nativo (urllib)

class Sessao:
    def __init__(self, conta):
        self.email        = conta["email"]
        self.senha        = conta["senha"]
        self.email_senha  = conta.get("email_senha", "")
        self.regioes      = conta["regioes"]
        self.cookie_jar   = http.cookiejar.CookieJar()
        self.opener       = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.logs         = []

    def log(self, msg):
        self.logs.append(msg)

    def buscar_codigo_email(self, tentativas=6, intervalo=2):
        import email.utils
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
        if not SUPABASE_URL or not SUPABASE_KEY: return None
        try:
            url = f"{SUPABASE_URL}/rest/v1/frota_tokens?select=jwt&email=eq.{urllib.parse.quote(self.email)}"
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and len(data) > 0:
                    return data[0].get("jwt")
                self.log("JWT nao encontrado no banco para este email")
        except urllib.error.HTTPError as he:
            self.log(f"Erro carregar JWT HTTPError: {he.code} {he.reason}")
        except Exception as e:
            self.log(f"Erro carregar JWT: {str(e)}")
        return None

    def salvar_jwt(self, jwt):
        if not SUPABASE_URL or not SUPABASE_KEY: return
        try:
            url = f"{SUPABASE_URL}/rest/v1/frota_tokens"
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
            body = json.dumps([{"email": self.email, "jwt": jwt}]).encode("utf-8")
            req = urllib.request.Request(url, headers=headers, data=body, method="POST")
            with urllib.request.urlopen(req) as resp:
                pass
            self.log("JWT salvo no banco")
        except urllib.error.HTTPError as he:
            self.log(f"Erro salvar JWT HTTPError: {he.code} {he.reason}")
        except Exception as e:
            self.log(f"Erro salvar JWT: {str(e)}")

    def get_cookie(self, nome):
        for c in self.cookie_jar:
            if c.name == nome:
                return c.value
        return None

    def fazer_request(self, url, headers_extra=None, body=None, tentativas=2):
        for tentativa in range(tentativas):
            jwt = self.carregar_jwt()
            cookie = f"entregolog_jwt={jwt}" if jwt else ""
            h = {**HEADERS_BASE, "cookie": cookie, **(headers_extra or {})}
            req = urllib.request.Request(url, headers=h, data=body)
            try:
                with self.opener.open(req, timeout=10) as resp:
                    raw = resp.read()
                    try:
                        return json.loads(raw.decode("utf-8"))
                    except:
                        return {}
            except urllib.error.HTTPError as e:
                if e.code == 401 and tentativa < tentativas - 1:
                    self.renovar_jwt()
                    continue
                raise
            except Exception as e:
                continue
        return {}

    def solicitar_codigo(self):
        self.cookie_jar.clear()
        body = json.dumps({"email": self.email, "password": self.senha}).encode("utf-8")
        h = {**HEADERS_BASE, "content-type": "application/json; charset=UTF-8", "cookie": ""}
        req = urllib.request.Request(URL_VALIDATE, headers=h, data=body)
        with self.opener.open(req) as resp:
            resp.read()
        self.log("Solicitado novo codigo de auth")

    def autenticar(self, codigo, jwt_antigo):
        self.cookie_jar.clear()
        body = json.dumps({"email": self.email, "code": codigo}).encode("utf-8")
        h = {**HEADERS_BASE, "content-type": "application/json; charset=UTF-8", "cookie": f"entregolog_jwt={jwt_antigo}" if jwt_antigo else ""}
        req = urllib.request.Request(URL_TOKEN, headers=h, data=body)
        with self.opener.open(req) as resp:
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

    def buscar_subpracas(self, region_uuid):
        params = urllib.parse.urlencode({"regionUuid": region_uuid})
        dados = self.fazer_request(f"{URL_SUBREGIONS}?{params}")
        return dados if isinstance(dados, list) else []

    def buscar_origens(self, region_uuid):
        params = urllib.parse.urlencode({"regionUuid": region_uuid})
        dados = self.fazer_request(f"{URL_ORIGINS}?{params}")
        return dados if isinstance(dados, list) else []

    def buscar_status_rapido(self, region_uuid, sub_uuid=None, origin_uuid=None):
        params = {"regionUuid": region_uuid, "status": "WORKING", "page": 0, "limit": 1}
        if sub_uuid: params["subRegionUuid"] = sub_uuid
        if origin_uuid: params["originUuid"] = origin_uuid
        dados = self.fazer_request(f"{URL_FROTA}?{urllib.parse.urlencode(params)}")
        counts = dados.get("driverCurrentStatus", {})
        return {
            "working": counts.get("working", 0),
            "offline": counts.get("offline", 0),
            "paused": counts.get("paused", 0),
            "blocked": counts.get("blocked", 0),
            "available": counts.get("available", 0),
        }

def montar_registro(horario, regiao, praca, subpraca, status):
    t = status.get("working", 0)
    o = status.get("offline", 0)
    p = status.get("paused", 0)
    b = status.get("blocked", 0)
    d = status.get("available", 0)
    total = t + o + p + b + d
    
    def pct(v): return f"{round(v / total * 100, 2):.2f}%" if total > 0 else "0.00%"
    
    return {
        "horario": horario,
        "regiao": regiao,
        "praca": praca,
        "subpraca": subpraca,
        "trabalhando": t,
        "offline": o,
        "em_pausa": p,
        "bloqueados": b,
        "disponiveis": d,
        "total": total,
        "pct_trabalhando": pct(t),
        "pct_offline": pct(o),
        "pct_em_pausa": pct(p),
        "pct_bloqueados": pct(b),
        "pct_disponiveis": pct(d)
    }

def coletar_regiao(sessao, regiao, horario):
    registros = []
    prefixo = PREFIXO_DEDICADO.get(regiao["nome"], "DEDICADO")
    subpracas = sessao.buscar_subpracas(regiao["uuid"])
    origens = sessao.buscar_origens(regiao["uuid"])
    
    geral = sessao.buscar_status_rapido(regiao["uuid"])
    registros.append(montar_registro(horario, regiao["nome"], regiao["nome"], "GERAL", geral))
    
    # Para rodar rapido na Vercel, omitimos a paginacao completa do LIVRE por enquanto 
    # ou podemos colocar '0' se precisar de performance
    # livre = sessao.calcular_livre(regiao["uuid"]) # MUITO LENTO PARA VERCEL
    
    for sub in subpracas:
        st = sessao.buscar_status_rapido(regiao["uuid"], sub_uuid=sub["uuid"])
        registros.append(montar_registro(horario, regiao["nome"], regiao["nome"], sub["name"], st))
        
    status_origens = []
    for origem in origens:
        st = sessao.buscar_status_rapido(regiao["uuid"], origin_uuid=origem["uuid"])
        status_origens.append((origem, st))
        
    if status_origens:
        ded_geral = {
            "working": sum(s["working"] for _, s in status_origens),
            "offline": sum(s["offline"] for _, s in status_origens),
            "paused": sum(s["paused"] for _, s in status_origens),
            "blocked": sum(s["blocked"] for _, s in status_origens),
            "available": sum(s["available"] for _, s in status_origens),
        }
        registros.append(montar_registro(horario, regiao["nome"], f"{prefixo} DEDICADO", "GERAL", ded_geral))
        
    for origem, st in status_origens:
        registros.append(montar_registro(horario, regiao["nome"], f"{prefixo} DEDICADO", origem["name"], st))
        
    return registros

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Erro: SUPABASE_URL ou SUPABASE_KEY nao configurados.")
            return

        horario = time.strftime("%Y-%m-%d %H:%M")
        sessoes = [Sessao(c) for c in CONTAS if c.get("ativo", True)]
        
        logs_finais = {}
        todos_registros = []
        erros = []
        for sessao in sessoes:
            for regiao in sessao.regioes:
                try:
                    registros = coletar_regiao(sessao, regiao, horario)
                    todos_registros.extend(registros)
                except Exception as e:
                    erros.append(f"Erro coletar {regiao['nome']}: {str(e)}")
                    try:
                        sucesso_renovacao = sessao.renovar_jwt()
                        if sucesso_renovacao:
                            try:
                                registros = coletar_regiao(sessao, regiao, horario)
                                todos_registros.extend(registros)
                            except Exception as e2:
                                erros.append(f"Erro pos-renovacao {regiao['nome']}: {str(e2)}")
                        else:
                            erros.append(f"Falha renovar JWT para {sessao.email}")
                    except Exception as e3:
                        erros.append(f"Erro no renovar_jwt: {str(e3)}")
            logs_finais[sessao.email] = sessao.logs
                            
        # Limpar registros do mesmo horario ou todos daquela região (depende da regra, aqui inserimos novo lote)
        # O ideal é apenas inserir
        if todos_registros:
            try:
                url = f"{SUPABASE_URL}/rest/v1/frota_metricas"
                headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
                body = json.dumps(todos_registros).encode("utf-8")
                req = urllib.request.Request(url, headers=headers, data=body, method="POST")
                with urllib.request.urlopen(req) as resp:
                    pass
            except Exception as e:
                erros.append(f"Erro ao inserir no Supabase: {str(e)}")

        self.send_response(200)
        self.send_header('Content-type','application/json')
        self.end_headers()
        res = {"status": "ok", "inserted": len(todos_registros), "erros": erros, "logs": logs_finais}
        self.wfile.write(json.dumps(res).encode('utf-8'))
        return
