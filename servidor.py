# Exportador Bling: servidor local. Uso: python servidor.py  -> abre http://localhost:8766
# Guarda a conexão com o Bling na pasta "dados" do seu computador; nada vai para outro lugar.
import functools, http.server, json, os, socketserver, sys, threading, time, traceback, unicodedata, urllib.parse, webbrowser

import atualizador, validador
from bling import Bling, BlingDemo, ErroBling, gravar, ler

PORT = 8766
ROOT = os.path.dirname(os.path.abspath(__file__))
CALLBACK = f'http://localhost:{PORT}/auth/callback'

real, demo = Bling(), BlingDemo()
nova_versao = {'sha': None}


def procurar_atualizacoes():
    # confere o GitHub a cada 3 minutos; a tela mostra o aviso "Nova versão"
    while True:
        time.sleep(180)
        nova_versao['sha'] = atualizador.tem_atualizacao()


def reiniciar(codigo):
    # o iniciar.bat abre o servidor de novo quando ele sai com 3 ou 4; fora dele, reinicia por aqui
    if os.environ.get('EXPORTADOR_REINICIA'):
        os._exit(codigo)
    args = [os.path.join(ROOT, 'servidor.py')] + [a for a in sys.argv[1:] if a != '--sem-navegador'] + (['--sem-navegador'] if codigo == 3 else [])
    os.execv(sys.executable, [sys.executable] + args)


def cliente():
    return demo if (ler('config.json') or {}).get('demo') else real


def mk_do_canal(tipo, regras):
    t = (tipo or '').lower().replace(' ', '')
    for chave, r in regras.items():
        if any(t == x.lower().replace(' ', '') for x in r['tipos_bling']):
            return chave
    return 'generico'


def registrar_conexao(etapa, detalhe=''):
    # mostra na janela preta e guarda para a tela explicar onde a conexão parou
    print(f'[conexão] {etapa} {detalhe}'.strip())
    gravar('conexao.json', {'etapa': etapa, 'detalhe': detalhe, 'quando': time.time()})


def resumo_bling(p):
    # o que o Bling mandou de imagens: aparece em "Ver o que veio do Bling" para conferir
    return {'imagens': validador.links_imagens(p),
            'midia': {k: p.get(k) for k in ('midia', 'imagemURL', '_imagemURL') if k in p}}


catalogo = {'itens': [], 'quando': 0, 'demo': None, 'trava': threading.Lock()}


def normalizar(s):
    s = unicodedata.normalize('NFD', str(s or '').lower())
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def buscar(b, pesquisa):
    # a busca do Bling só acha o começo do nome; aqui procura cada palavra em qualquer parte
    # do nome, SKU ou GTIN. A lista completa fica guardada por 10 minutos.
    with catalogo['trava']:
        demo_agora = b is demo
        if time.time() - catalogo['quando'] > 600 or catalogo['demo'] != demo_agora:
            catalogo['itens'] = b.catalogo()
            catalogo['quando'], catalogo['demo'] = time.time(), demo_agora
    palavras = normalizar(pesquisa).split()
    achados = [p for p in catalogo['itens']
               if all(w in normalizar(f"{p.get('nome')} {p.get('codigo')} {p.get('gtin')}") for w in palavras)]
    return achados[:300], len(catalogo['itens'])


def opcoes():
    c = ler('config.json') or {}
    return {'marca_padrao': c.get('marca_padrao', '')}


def verificar(b, pid, mk):
    regras = validador.carregar_regras()
    p = b.produto(pid)
    corrigido, correcoes, problemas = validador.verificar(p, mk, regras, opcoes())
    return p, corrigido, correcoes, problemas


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def responder(self, status, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def redirecionar(self, url):
        self.send_response(302)
        self.send_header('Location', url)
        self.end_headers()

    def corpo(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if not (u.path.startswith('/api/') or u.path.startswith('/auth/')):
            return super().do_GET()
        self.tratar(u.path, q, None)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        self.tratar(u.path, {}, self.corpo())

    def tratar(self, rota, q, dados):
        # só aceita chamadas desta própria tela (protege a sua conta do Bling contra outros sites)
        origem = self.headers.get('Origin')
        if dados is not None and origem and origem not in (f'http://localhost:{PORT}', f'http://127.0.0.1:{PORT}'):
            return self.responder(403, {'erro': 'Origem não permitida'})
        try:
            self.rotear(rota, q, dados)
        except ErroBling as e:
            self.responder(502 if e.status != 401 else 401,
                           {'erro': 'bling', 'status': e.status, 'detalhes': validador.traduzir_erro_bling(e.corpo)})
        except Exception as e:
            traceback.print_exc()
            self.responder(500, {'erro': str(e)})

    def rotear(self, rota, q, d):
        regras = validador.carregar_regras()
        c = ler('config.json') or {}
        b = cliente()

        if rota == '/api/estado':
            return self.responder(200, {
                'configurado': bool(c.get('client_id') and c.get('client_secret')), 'demo': bool(c.get('demo')),
                'conectado': b.conectado(), 'callback': CALLBACK, 'marca_padrao': c.get('marca_padrao', ''),
                'client_id': c.get('client_id', ''), 'versao': atualizador.versao_local()[:7],
                'atualizacao': bool(nova_versao['sha']), 'conexao': ler('conexao.json') or {},
                'marketplaces': {k: {'nome': r['nome'], 'titulo_max': r['titulo_max']} for k, r in regras.items()}})

        if rota == '/api/config':
            novo = {**c, **{k: v for k, v in d.items() if k in ('client_id', 'client_secret', 'marca_padrao', 'demo')}}
            gravar('config.json', novo)
            return self.responder(200, {'ok': True})

        if rota == '/auth/login':
            if not (c.get('client_id') and c.get('client_secret')):
                registrar_conexao('faltam_credenciais')
                return self.redirecionar('/?erro=configure')  # a tela explica o que falta
            url = real.url_login()
            registrar_conexao('foi_ao_bling', url.split('&state=')[0])
            return self.redirecionar(url)

        if rota == '/api/colar-retorno':
            # o Bling mandou para outro site (ex.: google.com/?code=...&state=...): a pessoa cola o endereço aqui
            qs = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(d.get('url', '').strip()).query))
            if 'code' not in qs:
                return self.responder(400, {'erro': 'Esse endereço não tem o código do Bling (procure por "code=" no endereço).'})
            registrar_conexao('bling_voltou', 'endereço colado')
            try:
                real.trocar_codigo(qs['code'], qs.get('state'))
            except ErroBling as e:
                msg = ' '.join(x['mensagem'] for x in validador.traduzir_erro_bling(e.corpo))
                registrar_conexao('erro_token', msg)
                return self.responder(400, {'erro': 'Não consegui conectar: ' + msg +
                                            ' O código vale poucos minutos: clique em "Salvar e conectar ao Bling" e cole o endereço novo logo em seguida.'})
            registrar_conexao('conectado')
            gravar('config.json', {**c, 'demo': False})
            return self.responder(200, {'ok': True})

        if rota == '/auth/callback':
            registrar_conexao('bling_voltou', 'com código' if 'code' in q else json.dumps(q, ensure_ascii=False))
            if 'code' not in q:
                motivo = q.get('error_description') or q.get('error') or 'a autorização foi cancelada ou recusada'
                return self.redirecionar('/?erro=' + urllib.parse.quote('O Bling não autorizou: ' + motivo))
            try:
                real.trocar_codigo(q['code'], q.get('state'))
            except Exception as e:
                if not isinstance(e, ErroBling):
                    traceback.print_exc()
                    e = ErroBling(0, {'error': {'message': f'Erro inesperado ({e}).'}})
                msg = ' '.join(x['mensagem'] for x in validador.traduzir_erro_bling(e.corpo))
                if e.status in (400, 401):
                    msg += ' Confira se o Client ID e o Client Secret foram copiados inteiros, sem espaço no fim.'
                registrar_conexao('erro_token', msg)
                return self.redirecionar('/?erro=' + urllib.parse.quote('Não consegui conectar: ' + msg))
            registrar_conexao('conectado')
            gravar('config.json', {**c, 'demo': False})
            return self.redirecionar('/?conectado=1')

        if rota == '/api/atualizar':
            sha = nova_versao['sha'] or atualizador.tem_atualizacao()
            if not sha:
                return self.responder(200, {'ok': True, 'atualizado': False})
            atualizador.atualizar(sha)
            self.responder(200, {'ok': True, 'atualizado': True})
            threading.Timer(0.5, reiniciar, [3]).start()
            return

        if rota == '/api/desconectar':
            real.desconectar()
            registrar_conexao('desconectado')
            return self.responder(200, {'ok': True})

        if rota == '/api/canais':
            canais = [{'id': x['id'], 'nome': x.get('descricao'), 'tipo': x.get('tipo'),
                       'marketplace': mk_do_canal(x.get('tipo'), regras), 'ativo': x.get('situacao', 1) == 1}
                      for x in b.canais()]
            return self.responder(200, {'canais': canais})

        if rota == '/api/produtos':
            if q.get('pesquisa', '').strip():
                if q.get('recarregar'):
                    catalogo['quando'] = 0
                lista, total = buscar(b, q['pesquisa'])
                return self.responder(200, {'produtos': lista, 'busca': True, 'total_catalogo': total})
            return self.responder(200, {'produtos': b.produtos(int(q.get('pagina', 1)))})

        if rota == '/api/verificar':
            original, corrigido, correcoes, problemas = verificar(b, d['id'], d['marketplace'])
            return self.responder(200, {'id': d['id'], 'nome': corrigido.get('nome'), 'correcoes': correcoes,
                                        'problemas': problemas, 'status': validador.status(problemas),
                                        'bling': resumo_bling(original)})

        if rota == '/api/corrigir-campo':
            # o usuário digitou o valor na tela: salva no Bling e verifica de novo
            p = b.produto(d['id'])
            p = validador.aplicar_campo(p, d['campo'], d['valor'])
            b.salvar_produto(p)
            original, corrigido, correcoes, problemas = verificar(b, d['id'], d['marketplace'])
            return self.responder(200, {'id': d['id'], 'nome': corrigido.get('nome'), 'correcoes': correcoes,
                                        'problemas': problemas, 'status': validador.status(problemas),
                                        'bling': resumo_bling(original)})

        if rota == '/api/exportar':
            original, corrigido, correcoes, problemas = verificar(b, d['id'], d['marketplace'])
            erros = [x for x in problemas if x['nivel'] == 'erro']
            if erros:
                return self.responder(200, {'id': d['id'], 'nome': corrigido.get('nome'), 'resultado': 'bloqueado', 'problemas': problemas,
                                            'bling': resumo_bling(original),
                                            'correcoes': correcoes,
                                            'mensagem': 'Não enviei: corrija os itens em vermelho primeiro.'})
            salvo = False
            if correcoes and d.get('aplicar_correcoes', True):
                b.salvar_produto(corrigido)
                salvo = True
            base = corrigido if salvo else original
            ajuste = float(d.get('ajuste_preco') or 0)
            preco = round(float(base.get('preco') or 0) * (1 + ajuste / 100), 2)
            try:
                _, acao = b.vincular(base, int(d['loja_id']), preco)
            except ErroBling as e:
                return self.responder(200, {'id': d['id'], 'nome': corrigido.get('nome'), 'resultado': 'recusado', 'correcoes': correcoes,
                                            'problemas': problemas, 'detalhes': validador.traduzir_erro_bling(e.corpo),
                                            'mensagem': 'O Bling recusou o envio.'})
            return self.responder(200, {'id': d['id'], 'nome': base.get('nome'), 'resultado': 'enviado', 'acao': acao, 'preco': preco,
                                        'correcoes': correcoes if salvo else [], 'problemas': problemas,
                                        'mensagem': ('Anúncio vinculado à loja' if acao == 'criado' else 'Anúncio atualizado na loja')
                                        + f' por R$ {preco:.2f}.'})

        self.responder(404, {'erro': 'rota não encontrada'})


if __name__ == '__main__':
    if '--sem-atualizar' not in sys.argv:
        print('Procurando atualizações...')
        sha = atualizador.tem_atualizacao()
        if sha:
            print('Baixando a versão nova...')
            try:
                atualizador.atualizar(sha)
                reiniciar(4)
            except Exception as e:
                print(f'Não consegui atualizar ({e}). Abrindo a versão atual.')
        threading.Thread(target=procurar_atualizacoes, daemon=True).start()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    pagina = functools.partial(Handler, directory=os.path.join(ROOT, 'web'))
    with socketserver.ThreadingTCPServer(('127.0.0.1', PORT), pagina) as srv:
        url = f'http://localhost:{PORT}'
        print(f'Exportador Bling rodando em {url}  (feche esta janela para parar)')
        if '--sem-navegador' not in sys.argv:
            webbrowser.open(url)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
