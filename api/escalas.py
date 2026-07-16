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

# URLS
URL_VALIDATE   = "https://api.entregolog.com/logistics-web-bff/operation/users/authentication/validate"
URL_TOKEN      = "https://api.entregolog.com/logistics-web-bff/operation/users/authentication/token"
URL_REFRESH    = "https://api.entregolog.com/logistics-web-bff/operation/users/authentication/token/refresh"
URL_ESCALAS    = "https://api.entregolog.com/logistics-web-bff/operation/v2.0/logistics-operator/shift-schedules"

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

LIMITE = 1000

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
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and len(data) > 0:
                    self.jwt_local = data[-1].get("jwt")
                    return self.jwt_local
                self.log("JWT nao encontrado no banco para este email")
        except urllib.error.HTTPError as he:
            self.log(f"Erro carregar JWT HTTPError: {he.code} {he.reason}")
        except Exception as e:
            self.log(f"Erro carregar JWT: {str(e)}")
        return None

    def salvar_jwt(self, jwt):
        self.jwt_local = jwt
        supa_url = SUPABASE_URL.rstrip('/') if SUPABASE_URL else ""
        if not supa_url or not SUPABASE_KEY: return
        try:
            url = f"{supa_url}/rest/v1/frota_tokens?email=eq.{urllib.parse.quote(self.email)}"
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
            body = json.dumps({"jwt": jwt}).encode("utf-8")
            req = urllib.request.Request(url, headers=headers, data=body, method="PATCH")
            with urllib.request.urlopen(req) as resp:
                pass
            self.log("JWT salvo no banco (PATCH)")
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

    def buscar_pagina_escalas(self, page, data_inicio, data_fim):
        params = urllib.parse.urlencode({
            "dateFrom": data_inicio,
            "dateTo":   data_fim,
            "page":     page,
            "limit":    LIMITE,
        })
        return self.fazer_request(f"{URL_ESCALAS}?{params}")

    def extrair_todas_escalas(self, data_inicio, data_fim):
        dados = self.buscar_pagina_escalas(1, data_inicio, data_fim)
        total = dados.get("total", 0)
        registros = dados.get("values", [])
        paginas = (total + LIMITE - 1) // LIMITE
        for p in range(2, paginas + 1):
            resp = self.buscar_pagina_escalas(p, data_inicio, data_fim)
            registros.extend(resp.get("values", []))
        return registros

PREFIXO_DEDICADO = {
    "Sao Paulo":          "SP",
    "Rio - Madureira":    "RJ",
    "Rio - Barra":        "RJ",
    "Rio - Zona Sul":     "RJ",
    "Rio - Campo Grande": "RJ",
    "Niteroi":            "RJ"
}

def calcular_praca_subpraca(r, nome_regiao):
    regiao = r.get("region", {}).get("name") or ""
    sub    = r.get("subRegion", {}).get("name") or ""
    origem = r.get("origin", {}).get("name") or ""
    if origem:
        prefixo = PREFIXO_DEDICADO.get(nome_regiao, "DEDICADO")
        return f"{prefixo} DEDICADO", origem
    return regiao.upper(), sub if sub else "LIVRE"

def processar_escalas(sessao, data_alvo, horario_coleta, nome_regiao):
    registros_prontos = []
    try:
        registros = sessao.extrair_todas_escalas(data_alvo, data_alvo)
        for r in registros:
            praca, subpraca = calcular_praca_subpraca(r, nome_regiao)
            slots = r.get("maxRegularDrivers", 0)
            logados = r.get("reservedRegularDrivers", 0)
            pct = f"{round(logados / slots * 100, 1)}%" if slots > 0 else "0%"
            
            shift_name = r.get("shift", {}).get("name", "")
            data_reg = r.get("date", data_alvo)
            
            # Extrai o modal da lista 'modals' vinda do JSON
            modals_list = r.get("modals", [])
            if len(modals_list) == 1:
                modal = modals_list[0].get("name", "Todos")
            elif len(modals_list) > 1:
                names = [m.get("name", "").upper() for m in modals_list]
                if all("MOTO" in n for n in names):
                    modal = "MOTORCYCLE"
                elif all("BIKE" in n or "BICYCLE" in n or "PEDAL" in n for n in names):
                    modal = "BICYCLE"
                else:
                    modal = "Todos"
            else:
                modal = "Todos"
            
            registros_prontos.append({
                "regiao": nome_regiao,
                "data": data_reg,
                "turno": shift_name,
                "praca": praca,
                "subpraca": subpraca,
                "logados": logados,
                "slots": slots,
                "pct_logados": pct,
                "horario_coleta": horario_coleta,
                "modal": modal
            })
    except Exception as e:
        sessao.log(f"Erro em extrair_todas_escalas: {str(e)}")
        raise
    return registros_prontos

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Erro: SUPABASE_URL ou SUPABASE_KEY nao configurados.")
            return

        from urllib.parse import urlparse, parse_qs
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)
        idx_conta = query.get('conta', [None])[0]

        fuso_br = timezone(timedelta(hours=-3))
        now_br = datetime.now(fuso_br)
        
        data_alvo = now_br.strftime("%Y-%m-%d")
        horario_coleta = now_br.strftime("%Y-%m-%d %H:%M")
        
        todas_contas_ativas = [c for c in CONTAS if c.get("ativo", True)]
        if idx_conta is not None and idx_conta.isdigit():
            idx = int(idx_conta)
            if 0 <= idx < len(todas_contas_ativas):
                todas_contas_ativas = [todas_contas_ativas[idx]]

        sessoes = [Sessao(c) for c in todas_contas_ativas]
        
        logs_finais = {}
        todos_registros = []
        erros = []
        
        def processar_sessao(sessao):
            registros_sessao = []
            sessao_erros = []
            for regiao in sessao.regioes:
                try:
                    regs = processar_escalas(sessao, data_alvo, horario_coleta, regiao["nome"])
                    registros_sessao.extend(regs)
                except Exception as e:
                    sessao_erros.append(f"Erro coletar {regiao['nome']}: {str(e)}")
                    try:
                        if sessao.renovar_jwt():
                            regs = processar_escalas(sessao, data_alvo, horario_coleta, regiao["nome"])
                            registros_sessao.extend(regs)
                        else:
                            sessao_erros.append(f"Falha renovar JWT para {sessao.email}")
                    except Exception as e2:
                        sessao_erros.append(f"Erro pos-renovacao {regiao['nome']}: {str(e2)}")
            return registros_sessao, sessao_erros, sessao.logs, sessao.email

        with ThreadPoolExecutor(max_workers=3) as executor:
            futuros = [executor.submit(processar_sessao, s) for s in sessoes]
            for f in as_completed(futuros):
                try:
                    regs, errs, logs, email = f.result()
                    todos_registros.extend(regs)
                    erros.extend(errs)
                    logs_finais[email] = logs
                except Exception as e:
                    erros.append(f"Erro Thread: {str(e)}")
                            
        if todos_registros:
            try:
                supa_url = SUPABASE_URL.rstrip('/') if SUPABASE_URL else ""
                url = f"{supa_url}/rest/v1/frota_escalas"
                headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
                
                # Para evitar duplicatas do mesmo dia e turno/subpraca, deletamos antes as antigas do mesmo dia
                # Agora mantemos o historico para poder navegar pela tabela no tempo!
                # regioes_nomes = list(set([r["regiao"] for r in todos_registros]))
                # if regioes_nomes:
                #     import urllib.parse
                #     regioes_param = ",".join([urllib.parse.quote(f'"{n}"') for n in regioes_nomes])
                #     del_url = f"{supa_url}/rest/v1/frota_escalas?data=eq.{urllib.parse.quote(data_alvo)}&regiao=in.({regioes_param})"
                #     del_req = urllib.request.Request(del_url, headers=headers, method="DELETE")
                #     try:
                #         with urllib.request.urlopen(del_req) as resp:
                #             pass
                #     except Exception as edel:
                #         erros.append(f"Erro limpar duplicatas: {str(edel)}")

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
