# Verifica um produto do Bling contra as regras de um marketplace e corrige o que der.
# Cada problema vem com: o que está errado, se foi corrigido sozinho e, se não foi,
# o passo a passo para corrigir (no Bling ou direto na tela do exportador).
import copy, html, json, os, re

ROOT = os.path.dirname(os.path.abspath(__file__))


def carregar_regras():
    with open(os.path.join(ROOT, 'regras.json'), encoding='utf-8') as f:
        return json.load(f)['marketplaces']


# ---------- utilidades ----------

RE_EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')
RE_URL = re.compile(r'(https?://\S+|www\.\S+|\b\S+\.(com|com\.br|net|br)(/\S*)?\b)', re.I)
RE_FONE = re.compile(r'(\(?\b\d{2}\)?\s?)?\b9?\d{4}[-\s]?\d{4}\b')
RE_ZAP = re.compile(r'\b(whats\s?app|whatsapp|zap|wpp|telegram|instagram|insta|me chama|chama no)\b[^\n.]*', re.I)
RE_EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿️]')
RE_HTML = re.compile(r'<[^>]+>')

PEQUENAS = {'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'para', 'p/', 'com', 'a', 'o', 'as', 'os', 'por', 'no', 'na'}


def texto(v):
    return (v or '').strip() if isinstance(v, str) else ('' if v is None else str(v))


def espacos(s):
    return re.sub(r'\s+', ' ', s).strip()


def tirar_html(s):
    s = re.sub(r'<\s*br\s*/?>|</p>|</li>', '\n', s, flags=re.I)
    s = re.sub(r'<[^>]*$', '', RE_HTML.sub('', s))  # inclusive tag cortada no fim
    return html.unescape(s).replace('\xa0', ' ')


def gtin_valido(g):
    g = re.sub(r'\D', '', g or '')
    if len(g) not in (8, 12, 13, 14):
        return False
    soma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(g[:-1])))
    return (10 - soma % 10) % 10 == int(g[-1])


def capitalizar(titulo):
    # só mexe quando o título está todo em MAIÚSCULAS (os marketplaces derrubam a relevância)
    letras = [c for c in titulo if c.isalpha()]
    if not letras or sum(c.isupper() for c in letras) / len(letras) < 0.8:
        return titulo
    partes = []
    for i, p in enumerate(titulo.lower().split(' ')):
        if re.search(r'\d', p) and len(p) <= 6:  # códigos e medidas: 12V, 2X, H4
            partes.append(p.upper())
        elif i > 0 and p in PEQUENAS:
            partes.append(p)
        else:
            partes.append(p[:1].upper() + p[1:])
    return ' '.join(partes)


def cortar(s, limite):
    if len(s) <= limite:
        return s
    corte = s[:limite + 1].rsplit(' ', 1)[0]
    return corte.rstrip(' -,/') if len(corte) >= limite * 0.6 else s[:limite].rstrip()


def links_imagens(p):
    """Todos os links de imagem do produto, onde quer que o Bling coloque (externas, internas,
    imagemURL...). Ignora vídeo e miniaturas."""
    achados = []

    def andar(v, chave=''):
        if isinstance(v, dict):
            for k, x in v.items():
                if k.lower() in ('video', 'videos', 'linkminiatura', 'miniatura'):
                    continue
                andar(x, k)
        elif isinstance(v, list):
            for x in v:
                andar(x, chave)
        elif isinstance(v, str) and v.startswith(('http://', 'https://')) and chave.lower() in ('link', 'url', 'imagemurl', 'imagem', ''):
            if v not in achados:
                achados.append(v)

    andar(p.get('midia') or {})
    for k in ('imagemURL', 'imagemUrl', 'imagem', 'imagens', '_imagemURL'):
        andar(p.get(k))
    return achados


def contar_imagens(p):
    return len(links_imagens(p))


PERMITIDAS = {'p', 'br', 'ul', 'ol', 'li', 'b', 'strong', 'i', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'table', 'tr', 'td', 'th', 'tbody', 'thead'}


def limpar_html(s):
    # tira estilos copiados de outros sites (fonte, cor, tamanho) e tags que os marketplaces recusam
    def tag(m):
        fecha, nome = m.group(1), m.group(2).lower()
        if nome not in PERMITIDAS:
            return '\n' if nome in ('div',) and fecha else ''
        return f'<{fecha}{nome}{" /" if nome == "br" else ""}>'
    s = re.sub(r'<\s*(/?)\s*([a-zA-Z0-9]+)[^>]*>', tag, s)
    s = re.sub(r'<[^>]*$', '', s)  # tag cortada no fim
    s = re.sub(r'&nbsp;', ' ', s)
    s = s + '</p>' * max(0, s.count('<p>') - s.count('</p>'))
    return s


def dimensoes(p):
    d = p.get('dimensoes') or {}
    return [float(d.get(k) or 0) for k in ('largura', 'altura', 'profundidade')]


# ---------- guias de correção ----------

ONDE = {
    'nome': 'Cadastros › Produtos › abra o produto › campo "Nome"',
    'descricaoCurta': 'Cadastros › Produtos › abra o produto › campo "Descrição curta"',
    'gtin': 'Cadastros › Produtos › abra o produto › aba "Características" › campo "GTIN/EAN"',
    'marca': 'Cadastros › Produtos › abra o produto › aba "Características" › campo "Marca"',
    'peso': 'Cadastros › Produtos › abra o produto › aba "Características" › "Peso líquido" e "Peso bruto" (em kg)',
    'dimensoes': 'Cadastros › Produtos › abra o produto › aba "Características" › "Largura", "Altura" e "Profundidade" (da embalagem)',
    'imagens': 'Cadastros › Produtos › abra o produto › aba "Imagens" › "Adicionar imagens"',
    'preco': 'Cadastros › Produtos › abra o produto › campo "Preço venda"',
    'estoque': 'Suprimentos › Controle de estoque › lance a entrada do produto',
    'situacao': 'Cadastros › Produtos › abra o produto › campo "Situação" › Ativo',
    'codigo': 'Cadastros › Produtos › abra o produto › campo "Código (SKU)"',
}


def problema(campo, nivel, msg, guia, editar=None, dica=None):
    # editar: como a tela pode corrigir esse campo direto (o usuário digita e o exportador salva no Bling)
    return {'campo': campo, 'nivel': nivel, 'mensagem': msg, 'como_corrigir': guia,
            'onde_no_bling': ONDE.get(campo), 'editar': editar, 'dica': dica}


# ---------- verificação ----------

def verificar(produto, mk, regras, opcoes=None):
    """Retorna (produto_corrigido, correcoes, problemas).
    correcoes: o que foi ajustado sozinho. problemas: o que ainda precisa da sua ação."""
    opcoes = opcoes or {}
    r = regras[mk]
    p = copy.deepcopy(produto)
    correcoes, problemas = [], []

    def corrigir(campo, antes, depois, porque):
        if antes != depois:
            correcoes.append({'campo': campo, 'antes': antes, 'depois': depois, 'motivo': porque})

    # --- Título ---
    nome = texto(p.get('nome'))
    novo = espacos(RE_EMOJI.sub('', nome))
    for palavra in r['palavras_proibidas_titulo']:
        novo = espacos(re.sub(r'(?i)\b' + re.escape(palavra) + r'\b', '', novo))
    novo = re.sub(r'[!*#$%]+', '', novo).strip(' -|')
    novo = capitalizar(novo)
    if len(novo) > r['titulo_max']:
        novo = cortar(novo, r['titulo_max'])
    if novo != nome:
        corrigir('nome', nome, novo, f'Título ajustado às regras do {r["nome"]}: até {r["titulo_max"]} caracteres, '
                 'sem emojis, sem MAIÚSCULAS e sem palavras proibidas (frete grátis, promoção...).')
        p['nome'] = novo
    if len(novo) < r['titulo_min']:
        problemas.append(problema('nome', 'erro', f'Título muito curto ({len(novo)} caracteres; mínimo {r["titulo_min"]}).',
                                  'Escreva o que é o produto, marca, modelo e principal característica. Ex.: "Farol Dianteiro Gol G5 Lado Direito Cromado".',
                                  {'tipo': 'texto', 'max': r['titulo_max']}))

    # --- Descrição ---
    desc = texto(p.get('descricaoCurta'))
    nova = desc
    motivo = []
    if not r['descricao_html'] and RE_HTML.search(nova):
        motivo.append(f'tirei o HTML (o {r["nome"]} só aceita texto)')
        nova = tirar_html(nova)
    elif RE_HTML.search(nova) or '&nbsp;' in nova:
        limpa = limpar_html(nova)
        if espacos(limpa) != espacos(nova):
            motivo.append('tirei fontes, cores e estilos copiados de outros sites (o marketplace recusa ou mostra quebrado)')
            nova = limpa
    if r['remover_contato_descricao']:
        antes_contato = nova
        nova = RE_EMAIL.sub('', nova)
        nova = RE_URL.sub('', nova)
        nova = RE_FONE.sub(lambda m: m.group(0) if len(re.sub(r'\D', '', m.group(0))) < 10 else '', nova)
        nova = RE_ZAP.sub('', nova)
        # sobras como "ou ." ou "( )" depois de tirar os contatos
        nova = re.sub(r'\(\s*\)|\s+(ou|e)\s*(?=[.,;\n]|$)', '', nova, flags=re.I)
        nova = re.sub(r'(?i)\b(e-?mail|site|tel(efone)?|fone|celular|contato)\b\s*:?\s*(?=[,.;\n]|$|e\b|ou\b)', '', nova)
        for _ in range(2):
            nova = re.sub(r'\s*,\s*(?=[,.;\n]|$)|\s+(ou|e)\s*(?=[.,;\n]|$)', '', nova, flags=re.I)
        nova = re.sub(r'\s+([.,;])', r'\1', nova)
        nova = re.sub(r'([.,;])(\s*[.,;])+', r'\1', nova)
        nova = '\n'.join(l for l in nova.split('\n') if re.search(r'\w', l))
        if espacos(nova) != espacos(antes_contato):
            motivo.append('removi telefone, WhatsApp, e-mail ou links (os marketplaces bloqueiam contato fora da plataforma)')
    nova = re.sub(r'[ \t]+', ' ', nova)
    nova = re.sub(r'\n{3,}', '\n\n', nova).strip()
    if len(nova) < r['descricao_min']:
        base = []
        if nova and nova.lower() not in (p.get('nome') or '').lower():
            base.append(nova)
        base.append(p.get('nome') or '')
        marca = texto(p.get('marca'))
        if marca:
            base.append(f'Marca: {marca}.')
        if p.get('condicao') == 1:
            base.append('Produto novo.')
        l, a, pr = dimensoes(p)
        if l and a and pr:
            base.append(f'Medidas da embalagem: {l:g} x {a:g} x {pr:g} cm.')
        if p.get('pesoBruto'):
            base.append(f'Peso: {float(p["pesoBruto"]):g} kg.')
        com_html = bool(RE_HTML.search(nova))
        gerada = ('<br />\n' if com_html else '\n').join(b for b in base if b)
        if com_html:
            gerada += '</p>' * max(0, gerada.count('<p>') - gerada.count('</p>'))
        if len(gerada) >= r['descricao_min']:
            nova = gerada
            motivo.append('completei a descrição com os dados do produto (confira)')
    if len(nova) > r['descricao_max']:
        nova = cortar(nova, r['descricao_max'])
        motivo.append(f'cortei no limite de {r["descricao_max"]} caracteres')
    if not motivo:
        nova = desc  # só espaços diferentes: não vale regravar o produto
    if nova != desc:
        corrigir('descricaoCurta', desc, nova, (lambda t: t[:1].upper() + t[1:] + '.')('; '.join(motivo) or 'arrumei espaços e quebras de linha'))
        p['descricaoCurta'] = nova
    if len(nova) < r['descricao_min']:
        problemas.append(problema('descricaoCurta', 'erro', f'Descrição curta demais ({len(nova)} caracteres; mínimo {r["descricao_min"]}).',
                                  'Descreva para que serve, compatibilidade, material, medidas e o que vem na caixa.',
                                  {'tipo': 'textarea'}))

    # --- SKU ---
    if not texto(p.get('codigo')):
        sku = f'SKU-{p.get("id")}'
        corrigir('codigo', '', sku, 'O produto não tinha código (SKU); criei um a partir do ID do Bling.')
        p['codigo'] = sku

    # --- GTIN/EAN ---
    gtin = re.sub(r'\D', '', texto(p.get('gtin')))
    if gtin and gtin != texto(p.get('gtin')):
        corrigir('gtin', p.get('gtin'), gtin, 'Removidos espaços e traços do GTIN/EAN.')
        p['gtin'] = gtin
    if gtin and not gtin_valido(gtin):
        problemas.append(problema('gtin', 'erro', f'GTIN/EAN "{gtin}" é inválido (dígito verificador não confere).',
                                  'Copie o código de barras que está na embalagem (13 números, começa com 789 no Brasil). '
                                  'Não invente: o marketplace confere na base GS1 e bloqueia o anúncio.',
                                  {'tipo': 'numero_texto'}))
    elif not gtin and r['gtin_obrigatorio']:
        problemas.append(problema('gtin', 'erro', f'O {r["nome"]} exige GTIN/EAN (código de barras).',
                                  'Digite o código de barras da embalagem. Produto sem código de barras: solicite isenção de GTIN '
                                  f'no painel do {r["nome"]} ou compre códigos na GS1 Brasil (gs1br.org).',
                                  {'tipo': 'numero_texto'}))
    elif not gtin and r['gtin_recomendado']:
        problemas.append(problema('gtin', 'aviso', 'Sem GTIN/EAN: o anúncio pode perder relevância ou cair em categoria errada.',
                                  'Se a embalagem tiver código de barras, preencha.', {'tipo': 'numero_texto'}))

    # --- Marca ---
    marca = texto(p.get('marca'))
    if not marca and opcoes.get('marca_padrao') and r['marca_obrigatoria']:
        corrigir('marca', '', opcoes['marca_padrao'], 'Marca vazia: usei a marca padrão das Configurações.')
        p['marca'] = opcoes['marca_padrao']
    elif not marca and r['marca_obrigatoria']:
        problemas.append(problema('marca', 'erro', f'O {r["nome"]} exige a marca.',
                                  'Digite a marca do fabricante. Produto sem marca? Use "Genérica" ou o nome da sua loja. '
                                  'Dica: defina uma "Marca padrão" nas Configurações para preencher sozinho.',
                                  {'tipo': 'texto'}))

    # --- Peso ---
    pl, pb = float(p.get('pesoLiquido') or 0), float(p.get('pesoBruto') or 0)
    if pb == 0 and pl > 0:
        corrigir('pesoBruto', 0, pl, 'Peso bruto vazio: copiei o peso líquido.')
        p['pesoBruto'] = pb = pl
    if pl == 0 and pb > 0:
        corrigir('pesoLiquido', 0, pb, 'Peso líquido vazio: copiei o peso bruto.')
        p['pesoLiquido'] = pl = pb
    if pb == 0 and r['peso_obrigatorio']:
        problemas.append(problema('peso', 'erro', 'Produto sem peso: o frete não é calculado e o marketplace recusa.',
                                  'Pese o produto JÁ EMBALADO e digite em kg (ex.: 350 g = 0.35).',
                                  {'tipo': 'peso'}))
    elif pb > 200:
        problemas.append(problema('peso', 'aviso', f'Peso de {pb:g} kg parece alto. Será que foi digitado em gramas?',
                                  'O Bling usa kg: 500 g = 0.5.', {'tipo': 'peso'}))

    # --- Dimensões ---
    l, a, pr = dimensoes(p)
    if r['dimensoes_obrigatorias'] and not (l and a and pr):
        problemas.append(problema('dimensoes', 'erro', 'Faltam as medidas da embalagem (largura, altura e profundidade).',
                                  'Meça a caixa do envio com uma trena e digite em centímetros.',
                                  {'tipo': 'dimensoes'}))

    # --- Imagens ---
    n = contar_imagens(p)
    sem_midia = 'midia' not in p and not any(k in p for k in ('imagemURL', 'imagens', '_imagemURL'))
    if n < r['imagens_min'] and sem_midia:
        problemas.append(problema('imagens', 'aviso', 'Não consegui ler as imagens deste produto no Bling. Confira se ele tem foto antes de exportar.',
                                  'Se o produto tem imagem no Bling, pode exportar.'))
    elif n < r['imagens_min']:
        problemas.append(problema('imagens', 'erro', f'Produto sem imagem (o {r["nome"]} exige pelo menos {r["imagens_min"]}).',
                                  'Cole o link de uma imagem (JPG ou PNG, de preferência 1200x1200 com fundo branco) ou adicione no Bling.',
                                  {'tipo': 'imagem'}))
    elif n > r['imagens_max']:
        problemas.append(problema('imagens', 'aviso', f'{n} imagens: o {r["nome"]} só aceita {r["imagens_max"]}, as demais serão ignoradas.',
                                  'Deixe as melhores primeiro (a 1ª é a capa).'))

    # --- Preço ---
    preco = float(p.get('preco') or 0)
    if preco < r['preco_min']:
        problemas.append(problema('preco', 'erro', f'Preço R$ {preco:.2f} abaixo do mínimo do {r["nome"]} (R$ {r["preco_min"]:.2f}).',
                                  'Digite o preço de venda.', {'tipo': 'dinheiro'}))

    # --- Condição ---
    if r['condicao_obrigatoria'] and not p.get('condicao'):
        corrigir('condicao', p.get('condicao'), 1, 'Condição não informada: marquei como "Novo". Se for usado, altere no Bling.')
        p['condicao'] = 1

    # --- Situação e estoque ---
    if p.get('situacao') and p['situacao'] != 'A':
        problemas.append(problema('situacao', 'erro', 'Produto inativo no Bling.', 'Ative o produto no Bling.'))
    saldo = p.get('_saldo')
    if saldo is not None and saldo < r['estoque_min']:
        problemas.append(problema('estoque', 'aviso', f'Estoque {saldo:g}: o anúncio vai ficar pausado até ter estoque.',
                                  'Lance entrada no estoque do Bling.'))

    if p.get('formato') == 'V':
        problemas.append(problema('nome', 'aviso', 'Produto com variações: confira cada variação (cor, tamanho) no Bling.',
                                  'As variações herdam peso, medidas e imagens do produto pai, mas cada uma precisa do próprio GTIN.'))

    return p, correcoes, problemas


def status(problemas):
    if any(x['nivel'] == 'erro' for x in problemas):
        return 'erro'
    return 'aviso' if problemas else 'ok'


# ---------- aplicar um valor digitado na tela ----------

def aplicar_campo(p, campo, valor):
    p = copy.deepcopy(p)
    if campo in ('nome', 'descricaoCurta', 'marca', 'codigo'):
        p[campo] = texto(valor)
    elif campo == 'gtin':
        p['gtin'] = re.sub(r'\D', '', texto(valor))
    elif campo == 'preco':
        p['preco'] = float(str(valor).replace(',', '.'))
    elif campo == 'peso':
        kg = float(str(valor).replace(',', '.'))
        p['pesoBruto'] = p['pesoLiquido'] = kg
    elif campo == 'dimensoes':
        d = p.get('dimensoes') or {}
        d.update({k: float(str(valor[k]).replace(',', '.')) for k in ('largura', 'altura', 'profundidade')})
        d['unidadeMedida'] = 1  # centímetros
        p['dimensoes'] = d
    elif campo == 'imagens':
        m = p.setdefault('midia', {}).setdefault('imagens', {})
        m.setdefault('externas', []).append({'link': texto(valor)})
    elif campo == 'situacao':
        p['situacao'] = 'A'
    else:
        raise ValueError(f'Campo {campo} não pode ser editado por aqui.')
    return p


# ---------- tradução dos erros que o Bling devolve ----------

TRADUCOES = [
    (r'gtin|ean', 'gtin', 'O GTIN/EAN foi recusado. Confira o código de barras da embalagem.'),
    (r'marca', 'marca', 'A marca foi recusada ou está vazia.'),
    (r'peso', 'peso', 'Peso inválido. Use kg (ex.: 0.35).'),
    (r'largura|altura|profundidade|dimens', 'dimensoes', 'Medidas inválidas. Use centímetros da embalagem.'),
    (r'imagem|foto|image', 'imagens', 'Imagem recusada: use JPG/PNG acessível pela internet, mínimo 500x500.'),
    (r'pre[cç]o|price', 'preco', 'Preço recusado.'),
    (r'categoria|category', None, 'Categoria não mapeada. No Bling, abra o produto › aba "Lojas" › escolha a categoria do marketplace.'),
    (r'j[aá] (existe|vinculad|cadastrad)|duplic', None, 'Este produto já estava vinculado a esta loja.'),
    (r'token|unauthori|autoriza', None, 'A conexão com o Bling expirou. Clique em "Conectar ao Bling" de novo.'),
    (r'limite|too many|429', None, 'Muitas requisições ao Bling. Espere um minuto e tente de novo.'),
]


def traduzir_erro_bling(corpo):
    """corpo: JSON de erro da API v3 ({"error": {"message", "description", "fields": [...]}})."""
    err = (corpo or {}).get('error') or {}
    textos = [err.get('description') or err.get('message') or '']
    textos += [f.get('msg') or '' for f in err.get('fields') or []]
    saida = []
    for t in filter(None, textos):
        for padrao, campo, dica in TRADUCOES:
            if re.search(padrao, t, re.I):
                saida.append({'original': t, 'campo': campo, 'mensagem': dica, 'onde_no_bling': ONDE.get(campo)})
                break
        else:
            saida.append({'original': t, 'campo': None, 'mensagem': t, 'onde_no_bling': None})
    return saida or [{'original': json.dumps(corpo, ensure_ascii=False)[:300], 'campo': None,
                      'mensagem': 'O Bling recusou sem explicar. Veja a mensagem original abaixo.', 'onde_no_bling': None}]
