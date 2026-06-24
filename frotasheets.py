# FROTASHEETS - VERSAO CORRIGIDA
# Logica de coleta baseada no frota.py (paginacao, LIVRE, prefixo dedicado, tratamento 401)
# Saida: Google Sheets
# CORRECOES:
#   - cookie_jar.clear() antes de solicitar_codigo() para evitar contaminacao entre contas
#   - header "cookie": "" explicito no solicitar_codigo() para nao vazar JWT de outra conta
#   - try/except com log do corpo do erro 401 em solicitar_codigo()
#   - delay de 2s entre autenticacoes de contas diferentes
#   - autenticar() tambem limpa cookie_jar antes de fazer a requisicao de token
#   - Melhor tratamento de erros e logs mais detalhados

import urllib.request
import urllib.parse
import urllib.error
import json
import http.cookiejar
import os
import time
import pickle
import imaplib
import email
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import gspread
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ============================================================
# CONFIGURACOES
# ============================================================

PLANILHA_URL     = "https://docs.google.com/spreadsheets/d/1ChubWCQ7pjbbgis2TAda_oSxXzor1fhgDarcX4Yu-bE/edit"
ABA_NOME         = "frota"
CREDENCIAIS_JSON = "C:/escalas/client_secret_246955343617-2b2lc3lvasat9aa8lbb7up36k6n2ed8a.apps.googleusercontent.com.json"
TOKEN_PATH       = "C:/escalas/token_escalas.pkl"
SCOPES           = ["https://www.googleapis.com/auth/spreadsheets"]

# ============================================================
# IMAP
# ============================================================

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

ARQUIVO_JWT_BASE  = "jwt_frota_{}.txt"
HORA_INICIO = 6   # 06:00
HORA_FIM    = 2   # 02:00 (madrugada do dia seguinte)
INTERVALO_MINUTOS = 10

# ============================================================
# URLS
# ============================================================

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

COLUNAS = [
    "Horario", "Regiao", "Praca", "Subpraca",
    "Trabalhando", "Offline", "Em Pausa", "Bloqueados", "Disponiveis", "Total",
    "% Trabalhando", "% Offline", "% Em Pausa", "% Bloqueados", "% Disponiveis",
]

STATUS_LIST = ["BLOCKED", "WORKING", "OFFLINE", "PAUSED", "AVAILABLE"]

# ============================================================
# GOOGLE SHEETS
# ============================================================

def conectar_sheets():
    creds = None

    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENCIAIS_JSON, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "wb") as token:
            pickle.dump(creds, token)

    client   = gspread.authorize(creds)
    planilha = client.open_by_url(PLANILHA_URL)

    try:
        aba = planilha.worksheet(ABA_NOME)
    except Exception:
        aba = planilha.add_worksheet(title=ABA_NOME, rows="1000", cols="20")
        aba.append_row(COLUNAS)
        aba.format("A1:O1", {
            "backgroundColor": {"red": 0.122, "green": 0.361, "blue": 0.600},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "bold": True,
                "foregroundColor": {"red": 1, "green": 1, "blue": 1}
            }
        })

    return aba

# ============================================================
# SESSAO
# ============================================================

class Sessao:
    def __init__(self, conta):
        self.email        = conta["email"]
        self.senha        = conta["senha"]
        self.email_senha  = conta.get("email_senha", "")
        self.regioes      = conta["regioes"]
        self.jwt_file     = "C:/escalas/" + ARQUIVO_JWT_BASE.format(
            self.email.replace("@", "_").replace(".", "_")
        )
        self.cookie_jar   = http.cookiejar.CookieJar()
        self.opener       = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )

    # ----------------------------------------------------------
    # EMAIL / IMAP
    # ----------------------------------------------------------

    def buscar_codigo_email(self, tentativas=12, intervalo=5):
        """Conecta via IMAP e busca o codigo de verificacao da EntreGO."""
        import email.utils, datetime
        momento = datetime.datetime.now(datetime.timezone.utc)
        print(f"  [{self.email}] Aguardando codigo no email...")

        for tentativa in range(tentativas):
            try:
                imap = imaplib.IMAP4_SSL(IMAP_SERVIDOR, IMAP_PORTA)
                imap.login(self.email, self.email_senha)
                imap.select("INBOX")

                _, msgs = imap.search(None, '(UNSEEN FROM "naoresponda@entregolog.com")')
                ids = msgs[0].split()

                for uid in reversed(ids):
                    _, data = imap.fetch(uid, "(RFC822)")
                    msg = email.message_from_bytes(data[0][1])

                    # Ignora emails antigos (anteriores a esta solicitacao)
                    try:
                        ts = email.utils.parsedate_to_datetime(msg.get("Date", ""))
                        if ts < momento - datetime.timedelta(seconds=30):
                            continue
                    except Exception:
                        pass

                    # Extrai corpo
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
                        print(f"  [{self.email}] Codigo encontrado: {codigo}")
                        return codigo

                imap.logout()
            except Exception as e:
                print(f"  [{self.email}] Erro IMAP (tentativa {tentativa + 1}): {e}")

            time.sleep(intervalo)

        raise Exception(
            f"Codigo nao encontrado no email de {self.email} apos {tentativas} tentativas."
        )

    # ----------------------------------------------------------
    # JWT
    # ----------------------------------------------------------

    def carregar_jwt(self):
        if os.path.exists(self.jwt_file):
            jwt = open(self.jwt_file).read().strip()
            if jwt:
                return jwt
        return None

    def salvar_jwt(self, jwt):
        with open(self.jwt_file, "w") as f:
            f.write(jwt)

    def get_cookie(self, nome):
        for c in self.cookie_jar:
            if c.name == nome:
                return c.value
        return None

    # ----------------------------------------------------------
    # HTTP
    # ----------------------------------------------------------

    def fazer_request(self, url, headers_extra=None, body=None, tentativas=4):
        for tentativa in range(tentativas):
            jwt    = self.carregar_jwt()
            cookie = f"entregolog_jwt={jwt}" if jwt else ""
            h = {
                **HEADERS_BASE,
                "cookie": cookie,
                **(headers_extra or {})
            }
            req = urllib.request.Request(url, headers=h, data=body)
            try:
                with self.opener.open(req, timeout=20) as resp:
                    raw = resp.read()
                    try:
                        return json.loads(raw.decode("utf-8"))
                    except Exception:
                        return {}
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    espera = 5 * (tentativa + 1)
                    print(f"  429 Too Many Requests, aguardando {espera}s...")
                    time.sleep(espera)
                    continue
                if e.code == 401:
                    if tentativa < tentativas - 1:
                        print(f"  [{self.email}] 401 na requisicao, renovando JWT (tentativa {tentativa + 1})...")
                        self.renovar_jwt()
                        time.sleep(2)
                        continue
                raise
            except Exception as e:
                espera = 3 * (tentativa + 1)
                print(
                    f"  [{self.email}] Erro de conexao ({e}), aguardando {espera}s "
                    f"(tentativa {tentativa + 1})..."
                )
                time.sleep(espera)
                continue
        raise Exception("Falha persistente apos todas as tentativas")

    # ----------------------------------------------------------
    # AUTENTICACAO
    # ----------------------------------------------------------

    def solicitar_codigo(self):
        """
        CORRECAO: limpa o cookie_jar antes de solicitar o codigo para evitar
        que o JWT/cookies de outra conta contaminem esta requisicao.
        Tambem forca cookie vazio no header e loga o corpo em caso de erro 401.
        """
        # Limpa cookies antigos para nao contaminar a autenticacao desta conta
        self.cookie_jar.clear()

        body = json.dumps({"email": self.email, "password": self.senha}).encode("utf-8")
        h = {
            **HEADERS_BASE,
            "content-type":    "application/json; charset=UTF-8",
            "x-captcha-token": "",
            "cookie":          "",   # garante que nenhum JWT vazado seja enviado
        }
        req = urllib.request.Request(URL_VALIDATE, headers=h, data=body)
        try:
            with self.opener.open(req) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            corpo_erro = ""
            try:
                corpo_erro = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            print(f"  [{self.email}] Erro {e.code} ao solicitar codigo: {corpo_erro}")
            raise

    def autenticar(self, codigo, jwt_antigo):
        """
        CORRECAO: limpa cookie_jar antes de autenticar para evitar conflito
        com cookies de outra conta que possam ter ficado no jar.
        """
        # Limpa cookies antes de autenticar
        self.cookie_jar.clear()

        body = json.dumps({"email": self.email, "code": codigo}).encode("utf-8")
        h = {
            **HEADERS_BASE,
            "content-type": "application/json; charset=UTF-8",
            "cookie":       f"entregolog_jwt={jwt_antigo}" if jwt_antigo else "",
        }
        req = urllib.request.Request(URL_TOKEN, headers=h, data=body)
        try:
            with self.opener.open(req) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            corpo_erro = ""
            try:
                corpo_erro = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            print(f"  [{self.email}] Erro {e.code} ao autenticar: {corpo_erro}")
            raise

        jwt_novo = self.get_cookie("entregolog_jwt")
        if jwt_novo:
            self.salvar_jwt(jwt_novo)
            return jwt_novo
        return None

    def renovar_jwt(self):
        refresh = self.get_cookie("entregolog_refresh_jwt")
        if refresh:
            print(f"  [{self.email}] Tentando refresh token...")
            try:
                req = urllib.request.Request(
                    URL_REFRESH,
                    headers={
                        **HEADERS_BASE,
                        "cookie": f"entregolog_refresh_jwt={refresh}"
                    },
                    data=b""
                )
                req.get_method = lambda: "POST"
                with self.opener.open(req) as resp:
                    resp.read()
                jwt_novo = self.get_cookie("entregolog_jwt")
                if jwt_novo:
                    self.salvar_jwt(jwt_novo)
                    print(f"  [{self.email}] JWT renovado via refresh!")
                    return True
            except Exception as e:
                print(f"  [{self.email}] Refresh falhou: {e}")

        print(f"  [{self.email}] Fazendo login completo...")
        try:
            jwt_antigo = self.carregar_jwt()
            if not jwt_antigo:
                print(f"  [{self.email}] JWT salvo nao encontrado!")
                return False
            self.solicitar_codigo()
            time.sleep(2)
            codigo = self.buscar_codigo_email()
            jwt_novo = self.autenticar(codigo, jwt_antigo)
            if jwt_novo:
                print(f"  [{self.email}] Login completo realizado!")
                return True
            return False
        except Exception as e:
            print(f"  [{self.email}] Falha no login completo: {e}")
            return False

    # ----------------------------------------------------------
    # COLETA DE DADOS
    # ----------------------------------------------------------

    def buscar_subpracas(self, region_uuid):
        params = urllib.parse.urlencode({"regionUuid": region_uuid})
        dados  = self.fazer_request(f"{URL_SUBREGIONS}?{params}")
        return dados if isinstance(dados, list) else []

    def buscar_origens(self, region_uuid):
        params = urllib.parse.urlencode({"regionUuid": region_uuid})
        dados  = self.fazer_request(f"{URL_ORIGINS}?{params}")
        return dados if isinstance(dados, list) else []

    def buscar_todos_entregadores(self, region_uuid, sub_uuid=None, origin_uuid=None):
        """Busca todos os entregadores com paginacao, filtrando por status."""
        todos  = []
        vistos = set()

        for status in STATUS_LIST:
            page = 0
            while True:
                params = {
                    "regionUuid": region_uuid,
                    "status":     status,
                    "page":       page,
                    "limit":      50,
                }
                if sub_uuid:
                    params["subRegionUuid"] = sub_uuid
                if origin_uuid:
                    params["originUuid"] = origin_uuid

                dados   = self.fazer_request(f"{URL_FROTA}?{urllib.parse.urlencode(params)}")
                content = dados.get("content", [])
                total   = dados.get("total", 0)
                size    = dados.get("size", 50)

                for e in content:
                    uid = e.get("uuid")
                    if uid and uid not in vistos:
                        vistos.add(uid)
                        todos.append(e)

                if not content:
                    break

                if page * size + len(content) >= total:
                    break

                page += 1
                time.sleep(0.2)

        return todos

    def contabilizar(self, entregadores):
        """Converte lista de entregadores em dicionario de contagens."""
        status = {"working": 0, "offline": 0, "paused": 0, "blocked": 0, "available": 0}
        for e in entregadores:
            block   = e.get("blockState", "")
            connect = e.get("connectivityState", "")
            state   = e.get("state", "")

            if block == "BLOCKED":
                status["blocked"] += 1
            elif connect == "OFFLINE":
                status["offline"] += 1
            elif state == "PAUSED":
                status["paused"] += 1
            elif state == "WORKING":
                status["working"] += 1
            else:
                status["available"] += 1
        return status

    def buscar_status_rapido(self, region_uuid, sub_uuid=None, origin_uuid=None):
        """Usa driverCurrentStatus da API — 1 requisicao, sem paginacao."""
        params = {
            "regionUuid": region_uuid,
            "status":     "WORKING",
            "page":       0,
            "limit":      1,
        }
        if sub_uuid:
            params["subRegionUuid"] = sub_uuid
        if origin_uuid:
            params["originUuid"] = origin_uuid

        dados  = self.fazer_request(f"{URL_FROTA}?{urllib.parse.urlencode(params)}")
        counts = dados.get("driverCurrentStatus", {})

        return {
            "working":   counts.get("working",   0),
            "offline":   counts.get("offline",   0),
            "paused":    counts.get("paused",    0),
            "blocked":   counts.get("blocked",   0),
            "available": counts.get("available", 0),
        }

    def buscar_status(self, region_uuid, sub_uuid=None, origin_uuid=None):
        todos = self.buscar_todos_entregadores(region_uuid, sub_uuid=sub_uuid, origin_uuid=origin_uuid)
        return self.contabilizar(todos)

    def calcular_livre(self, region_uuid):
        """Entregadores sem subpraca e sem origem = LIVRE. Continua paginando."""
        todos  = self.buscar_todos_entregadores(region_uuid)
        livres = [e for e in todos if not e.get("subRegionName") and not e.get("originName")]
        return self.contabilizar(livres)

# ============================================================
# FORMATACAO
# ============================================================

def montar_linha(horario, regiao, praca, subpraca, status):
    t = status.get("working",   0)
    o = status.get("offline",   0)
    p = status.get("paused",    0)
    b = status.get("blocked",   0)
    d = status.get("available", 0)
    total = t + o + p + b + d

    def pct(v):
        return f"{round(v / total * 100, 2):.2f}%" if total > 0 else "0.00%"

    return [
        horario, regiao, praca, subpraca,
        t, o, p, b, d, total,
        pct(t), pct(o), pct(p), pct(b), pct(d),
    ]

# ============================================================
# COLETA
# ============================================================

def coletar_regiao(sessao, regiao, horario):
    linhas    = []
    prefixo   = PREFIXO_DEDICADO.get(regiao["nome"], "DEDICADO")
    subpracas = sessao.buscar_subpracas(regiao["uuid"])
    origens   = sessao.buscar_origens(regiao["uuid"])
    total_itens = len(subpracas) + len(origens)
    sleep_entre = 1.0 if total_itens > 15 else 0.5

    # GERAL — rapido
    geral = sessao.buscar_status_rapido(regiao["uuid"])
    linhas.append(montar_linha(horario, regiao["nome"], regiao["nome"], "GERAL", geral))

    # LIVRE — pagina uma vez a regiao inteira
    livre = sessao.calcular_livre(regiao["uuid"])
    linhas.append(montar_linha(horario, regiao["nome"], regiao["nome"], "LIVRE", livre))

    # Por subpraca — rapido
    for sub in subpracas:
        status = sessao.buscar_status_rapido(regiao["uuid"], sub_uuid=sub["uuid"])
        linhas.append(montar_linha(horario, regiao["nome"], regiao["nome"], sub["name"], status))
        time.sleep(sleep_entre)

    # Por origem (dedicado) — rapido
    status_origens = []
    for origem in origens:
        status = sessao.buscar_status_rapido(regiao["uuid"], origin_uuid=origem["uuid"])
        status_origens.append((origem, status))
        time.sleep(sleep_entre)

    # DEDICADO GERAL — soma de todas as origens, aparece primeiro
    if status_origens:
        ded_geral = {
            "working":   sum(s["working"]   for _, s in status_origens),
            "offline":   sum(s["offline"]   for _, s in status_origens),
            "paused":    sum(s["paused"]    for _, s in status_origens),
            "blocked":   sum(s["blocked"]   for _, s in status_origens),
            "available": sum(s["available"] for _, s in status_origens),
        }
        linhas.append(montar_linha(horario, regiao["nome"], f"{prefixo} DEDICADO", "GERAL", ded_geral))

    # Origens individuais
    for origem, status in status_origens:
        linhas.append(montar_linha(horario, regiao["nome"], f"{prefixo} DEDICADO", origem["name"], status))

    return linhas


def coletar(sessoes, aba):
    horario = time.strftime("%Y-%m-%d %H:%M")
    print(f"[{horario}] Coletando status da frota...")
    todas_linhas = []

    def coletar_sessao(sessao):
        linhas_sessao = []
        for regiao in sessao.regioes:
            try:
                linhas = coletar_regiao(sessao, regiao, horario)
                linhas_sessao.extend(linhas)
                print(f"  {regiao['nome']}: {len(linhas)} linhas coletadas.")
            except Exception as e:
                if "401" in str(e):
                    print(f"  {regiao['nome']}: JWT expirado, renovando...")
                    if sessao.renovar_jwt():
                        try:
                            linhas = coletar_regiao(sessao, regiao, horario)
                            linhas_sessao.extend(linhas)
                            print(f"  {regiao['nome']}: {len(linhas)} linhas coletadas apos renovacao.")
                        except Exception as e2:
                            print(f"  {regiao['nome']}: Erro apos renovacao: {e2}")
                    else:
                        print(f"  {regiao['nome']}: Nao foi possivel renovar JWT.")
                else:
                    print(f"  {regiao['nome']}: Erro: {e}")
        return linhas_sessao

    with ThreadPoolExecutor(max_workers=len(sessoes)) as ex:
        futures = {ex.submit(coletar_sessao, s): s for s in sessoes}
        resultados = {s.email: [] for s in sessoes}
        for f in as_completed(futures):
            resultados[futures[f].email] = f.result()

    # Manter ordem original das contas
    for sessao in sessoes:
        todas_linhas.extend(resultados[sessao.email])

    if todas_linhas:
        aba.insert_rows(todas_linhas, row=2)
        print(f"[{horario}] {len(todas_linhas)} linhas inseridas no topo do Sheets!\n")
    else:
        print(f"[{horario}] Nenhuma linha coletada.\n")

# ============================================================
# MAIN
# ============================================================

def autenticar_conta(sessao):
    """
    CORRECAO: encapsula o fluxo de autenticacao de uma conta com logs detalhados.
    Adiciona delay entre solicitar_codigo e autenticar para dar tempo ao servidor
    processar o envio do email.
    """
    print(f"\nConta: {sessao.email}")
    try:
        sessao.solicitar_codigo()
    except Exception as e:
        raise Exception(f"Falha ao solicitar codigo para {sessao.email}: {e}")

    # Aguarda o email chegar antes de tentar ler
    time.sleep(3)

    codigo = sessao.buscar_codigo_email()
    jwt_antigo = sessao.carregar_jwt() or ""
    jwt_novo = sessao.autenticar(codigo, jwt_antigo)
    if not jwt_novo:
        raise Exception(f"Autenticacao falhou para {sessao.email} — JWT nao retornado.")
    print(f"Login OK: {sessao.email}\n")


if __name__ == "__main__":
    try:
        aba     = conectar_sheets()
        sessoes = [Sessao(c) for c in CONTAS if c.get("ativo", True)]

        # CORRECAO: autentica cada conta sequencialmente com delay entre elas
        # para evitar que requests simultaneas causem 401 na API
        for i, sessao in enumerate(sessoes):
            autenticar_conta(sessao)
            if i < len(sessoes) - 1:
                print(f"  Aguardando 4s antes da proxima conta...\n")
                time.sleep(4)

        print(f"Iniciando coleta automatica a cada {INTERVALO_MINUTOS} minutos.")
        print(f"Horario ativo: {HORA_INICIO:02d}:00 ate {HORA_FIM:02d}:00.")
        print("Deixe essa janela aberta. Para parar feche a janela ou Ctrl+C.\n")

        while True:
            hora_atual = int(time.strftime("%H"))

            # Janela ativa: 06:00 ate 02:00 (atravessa meia-noite)
            ativo = hora_atual >= HORA_INICIO or hora_atual < HORA_FIM

            if ativo:
                coletar(sessoes, aba)
                print(f"Proxima coleta em {INTERVALO_MINUTOS} minutos...\n")
                time.sleep(INTERVALO_MINUTOS * 60)
            else:
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M')}] "
                    f"Fora do horario de coleta. Aguardando 06:00...",
                    end="\r"
                )
                time.sleep(60)

    except KeyboardInterrupt:
        print("\nColeta encerrada.")
    except Exception as e:
        print(f"\nErro: {e}")
        input("\nPressione Enter para fechar...")