# Cliente da API v3 do Bling (OAuth2) e um Bling de mentira para o modo demonstração.
import base64, copy, json, os, secrets, threading, time, urllib.error, urllib.parse, urllib.request

API = 'https://api.bling.com.br/Api/v3'
AUTORIZAR = 'https://www.bling.com.br/Api/v3/oauth/authorize'
TOKEN = 'https://api.bling.com.br/Api/v3/oauth/token'
ROOT = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(ROOT, 'dados')


class ErroBling(Exception):
    def __init__(self, status, corpo):
        super().__init__(f'Bling {status}')
        self.status, self.corpo = status, corpo


def ler(nome, padrao=None):
    try:
        with open(os.path.join(DADOS, nome), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def gravar(nome, valor):
    os.makedirs(DADOS, exist_ok=True)
    with open(os.path.join(DADOS, nome), 'w', encoding='utf-8') as f:
        json.dump(valor, f, ensure_ascii=False, indent=2)


class Bling:
    # O Bling aceita 3 requisições por segundo; o intervalo abaixo deixa folga.
    INTERVALO = 0.4

    def __init__(self):
        self.trava = threading.Lock()
        self.ultima = 0.0
        self.estado_oauth = None

    # ---- OAuth ----
    def config(self):
        return ler('config.json', {}) or {}

    def conectado(self):
        return bool((ler('token.json') or {}).get('access_token'))

    def url_login(self):
        estado = secrets.token_urlsafe(16)
        gravar('oauth_state.json', ([estado] + (ler('oauth_state.json') or []))[:5])
        q = urllib.parse.urlencode({'response_type': 'code', 'client_id': self.config()['client_id'].strip(),
                                    'state': estado})
        return f'{AUTORIZAR}?{q}'

    def _pedir_token(self, dados):
        c = self.config()
        basic = base64.b64encode(f'{c["client_id"].strip()}:{c["client_secret"].strip()}'.encode()).decode()
        req = urllib.request.Request(TOKEN, data=urllib.parse.urlencode(dados).encode(), method='POST', headers={
            'Authorization': f'Basic {basic}', 'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                tok = json.load(r)
        except urllib.error.HTTPError as e:
            raise ErroBling(e.code, _json(e.read()))
        except urllib.error.URLError as e:
            raise ErroBling(0, {'error': {'message': f'Sem conexão com o Bling ({e.reason}). Confira a internet, o antivírus ou o firewall.'}})
        tok['expira_em'] = time.time() + int(tok.get('expires_in', 21600)) - 120
        gravar('token.json', tok)
        return tok

    def trocar_codigo(self, code, state):
        validos = ler('oauth_state.json') or []
        if state not in validos:
            raise ErroBling(400, {'error': {'message': 'Retorno do Bling não confere (state). Tente conectar de novo.'}})
        gravar('oauth_state.json', [s for s in validos if s != state])
        return self._pedir_token({'grant_type': 'authorization_code', 'code': code})

    def _token(self):
        tok = ler('token.json') or {}
        if not tok.get('access_token'):
            raise ErroBling(401, {'error': {'message': 'Não conectado ao Bling.'}})
        if time.time() > tok.get('expira_em', 0):
            tok = self._pedir_token({'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token']})
        return tok['access_token']

    def desconectar(self):
        gravar('token.json', {})

    # ---- chamadas ----
    def chamar(self, metodo, caminho, corpo=None, tentativas=4):
        with self.trava:
            espera = self.ultima + self.INTERVALO - time.time()
            if espera > 0:
                time.sleep(espera)
            self.ultima = time.time()
        req = urllib.request.Request(API + caminho, method=metodo,
                                     data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers={'Authorization': f'Bearer {self._token()}', 'Accept': 'application/json',
                                              'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return _json(r.read())
        except urllib.error.HTTPError as e:
            corpo_erro = _json(e.read())
            if e.code == 429 and tentativas > 1:
                time.sleep(1.5)
                return self.chamar(metodo, caminho, corpo, tentativas - 1)
            if e.code == 401 and tentativas > 1:
                tok = ler('token.json') or {}
                if tok.get('refresh_token'):
                    tok['expira_em'] = 0
                    gravar('token.json', tok)
                    return self.chamar(metodo, caminho, corpo, 1)
            raise ErroBling(e.code, corpo_erro)
        except urllib.error.URLError as e:
            raise ErroBling(0, {'error': {'message': f'Sem conexão com o Bling ({e.reason}). Confira a internet.'}})

    def get(self, caminho, **q):
        q = {k: v for k, v in q.items() if v not in (None, '')}
        return self.chamar('GET', caminho + ('?' + urllib.parse.urlencode(q, doseq=True) if q else ''))

    # ---- recursos usados pelo exportador ----
    def canais(self):
        return self.get('/canais-venda').get('data', [])

    def produtos(self, pagina=1):
        return self.get('/produtos', pagina=pagina, limite=50, criterio=2).get('data', [])

    def catalogo(self):
        """Todos os produtos ativos (resumo), 100 por página. Usado na busca."""
        itens, pagina = [], 1
        while True:
            lote = self.get('/produtos', pagina=pagina, limite=100, criterio=2).get('data', [])
            itens += lote
            if len(lote) < 100 or pagina >= 300:
                return itens
            pagina += 1

    def produto(self, pid):
        p = self.get(f'/produtos/{pid}')['data']
        from validador import contar_imagens
        if not contar_imagens(p):
            # algumas contas trazem a foto só na listagem (campo imagemURL)
            try:
                lista = self.get('/produtos', **{'idsProdutos[]': pid}).get('data', [])
                if lista and lista[0].get('imagemURL'):
                    p['_imagemURL'] = lista[0]['imagemURL']
            except ErroBling:
                pass
        try:
            s = self.get('/estoques/saldos', **{'idsProdutos[]': pid}).get('data', [])
            p['_saldo'] = float(s[0].get('saldoVirtualTotal', 0)) if s else None
        except ErroBling:
            p['_saldo'] = None
        return p

    def salvar_produto(self, p):
        corpo = {k: v for k, v in p.items() if not k.startswith('_')}
        return self.chamar('PUT', f'/produtos/{p["id"]}', corpo)

    def vinculo(self, pid, loja_id):
        d = self.get('/produtos/lojas', idProduto=pid, idLoja=loja_id).get('data', [])
        return d[0] if d else None

    def vincular(self, p, loja_id, preco):
        corpo = {'codigo': p.get('codigo') or str(p['id']), 'preco': preco, 'produto': {'id': p['id']},
                 'loja': {'id': int(loja_id)}}
        atual = self.vinculo(p['id'], loja_id)
        if atual:
            return self.chamar('PUT', f'/produtos/lojas/{atual["id"]}', corpo), 'atualizado'
        return self.chamar('POST', '/produtos/lojas', corpo), 'criado'


def _json(b):
    try:
        return json.loads(b or b'{}')
    except ValueError:
        return {'error': {'message': b[:300].decode('utf-8', 'replace')}}


class BlingDemo(Bling):
    """Simula o Bling com produtos de exemplo, para testar a tela sem conta."""

    def __init__(self):
        super().__init__()
        self.base = {p['id']: p for p in copy.deepcopy(EXEMPLOS)}
        self.vinculos = {}

    def conectado(self):
        return True

    def canais(self):
        return [{'id': 9001, 'descricao': 'Minha loja Mercado Livre', 'tipo': 'MercadoLivre', 'situacao': 1},
                {'id': 9002, 'descricao': 'Shopee Oficial', 'tipo': 'Shopee', 'situacao': 1},
                {'id': 9003, 'descricao': 'Magalu', 'tipo': 'Magalu', 'situacao': 1},
                {'id': 9004, 'descricao': 'Amazon BR', 'tipo': 'Amazon', 'situacao': 1}]

    def produtos(self, pagina=1):
        return self.catalogo() if pagina == 1 else []

    def catalogo(self):
        return [{k: p.get(k) for k in ('id', 'nome', 'codigo', 'preco', 'situacao', 'formato', 'gtin')} for p in self.base.values()]

    def produto(self, pid):
        if int(pid) not in self.base:
            raise ErroBling(404, {'error': {'message': 'Produto não encontrado'}})
        return copy.deepcopy(self.base[int(pid)])

    def salvar_produto(self, p):
        time.sleep(0.15)
        self.base[int(p['id'])] = copy.deepcopy(p)
        return {'data': {'id': p['id']}}

    def vincular(self, p, loja_id, preco):
        time.sleep(0.25)
        if loja_id == 9003 and not p.get('gtin'):  # simula uma recusa do marketplace
            raise ErroBling(400, {'error': {'type': 'VALIDATION_ERROR', 'message': 'Não foi possível salvar',
                                            'fields': [{'msg': 'O campo GTIN é obrigatório para esta loja'}]}})
        chave = (p['id'], loja_id)
        acao = 'atualizado' if chave in self.vinculos else 'criado'
        self.vinculos[chave] = {'preco': preco}
        return {'data': {'id': 70000 + p['id']}}, acao


IMG = 'https://placehold.co/1200x1200/png'
EXEMPLOS = [
    {'id': 101, 'nome': 'FAROL DIANTEIRO GOL G5 LADO DIREITO CROMADO FRETE GRÁTIS!!! 🔥 PROMOÇÃO ENVIO IMEDIATO', 'codigo': 'FAR-G5-LD',
     'preco': 289.9, 'situacao': 'A', 'formato': 'S', 'gtin': '7891234567895', 'marca': 'Arteb', 'condicao': 0,
     'pesoLiquido': 2.1, 'pesoBruto': 0, 'dimensoes': {'largura': 45, 'altura': 25, 'profundidade': 30, 'unidadeMedida': 1},
     'descricaoCurta': '<p>Farol novo, encaixe perfeito.</p> Chama no WhatsApp (11) 98765-4321 ou www.minhaloja.com.br',
     'midia': {'imagens': {'externas': [{'link': IMG}, {'link': IMG}]}}, '_saldo': 12},
    {'id': 102, 'nome': 'Kit Pastilha de Freio Dianteira Onix 2013 a 2019 Cerâmica', 'codigo': 'PAS-ONX',
     'preco': 119.0, 'situacao': 'A', 'formato': 'S', 'gtin': '', 'marca': '', 'condicao': 1,
     'pesoLiquido': 0.9, 'pesoBruto': 1.0, 'dimensoes': {'largura': 18, 'altura': 6, 'profundidade': 14, 'unidadeMedida': 1},
     'descricaoCurta': 'Pastilha cerâmica de alta durabilidade, baixo ruído e pouco pó. Acompanha 4 pastilhas e graxa.',
     'midia': {'imagens': {'externas': [{'link': IMG}]}}, '_saldo': 30},
    {'id': 103, 'nome': 'Retrovisor Elétrico Corolla 2015 Esquerdo', 'codigo': '',
     'preco': 459.0, 'situacao': 'A', 'formato': 'S', 'gtin': '7891234567890', 'marca': 'Metagal', 'condicao': 1,
     'pesoLiquido': 0, 'pesoBruto': 0, 'dimensoes': {'largura': 0, 'altura': 0, 'profundidade': 0, 'unidadeMedida': 1},
     'descricaoCurta': 'Retrovisor', 'midia': {'imagens': {'externas': []}}, '_saldo': 3},
    {'id': 104, 'nome': 'Lâmpada Super Branca H4 12V 60/55W Par', 'codigo': 'LMP-H4',
     'preco': 49.9, 'situacao': 'A', 'formato': 'S', 'gtin': '7896543210982', 'marca': 'Philips', 'condicao': 1,
     'pesoLiquido': 0.12, 'pesoBruto': 0.15, 'dimensoes': {'largura': 10, 'altura': 6, 'profundidade': 12, 'unidadeMedida': 1},
     'descricaoCurta': 'Par de lâmpadas H4 super branca, luz 4300K, 12V 60/55W. Encaixe original, não precisa adaptar.',
     'midia': {'imagens': {'externas': [{'link': IMG}, {'link': IMG}, {'link': IMG}]}}, '_saldo': 80},
]
