# Mantém o exportador na versão mais nova do GitHub (duhdev/exportador-bling, branch main).
# Baixa o zip do repositório e copia por cima dos arquivos, sem mexer na pasta "dados"
# (sua conexão com o Bling) nem no iniciar.bat (o Windows lê esse arquivo enquanto ele roda).
import io, json, os, shutil, urllib.request, zipfile

REPO = 'duhdev/exportador-bling'
RAMO = 'main'
ROOT = os.path.dirname(os.path.abspath(__file__))
ARQ_VERSAO = os.path.join(ROOT, 'dados', 'versao.txt')
PRESERVAR = {'dados', 'iniciar.bat'}


def versao_local():
    try:
        with open(ARQ_VERSAO, encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


def versao_remota():
    """Commit mais recente do GitHub, ou None sem internet."""
    req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/commits/{RAMO}',
                                 headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'exportador-bling'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)['sha']
    except Exception:
        return None


def tem_atualizacao():
    remota = versao_remota()
    return remota if remota and remota != versao_local() else None


def atualizar(sha):
    req = urllib.request.Request(f'https://codeload.github.com/{REPO}/zip/{sha}', headers={'User-Agent': 'exportador-bling'})
    with urllib.request.urlopen(req, timeout=60) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    for item in z.infolist():
        partes = item.filename.split('/', 1)
        if len(partes) < 2 or not partes[1] or item.is_dir():
            continue
        rel = partes[1]
        if rel.split('/', 1)[0] in PRESERVAR:
            continue
        destino = os.path.join(ROOT, *rel.split('/'))
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with z.open(item) as src, open(destino + '.novo', 'wb') as dst:
            shutil.copyfileobj(src, dst)
        os.replace(destino + '.novo', destino)
    os.makedirs(os.path.dirname(ARQ_VERSAO), exist_ok=True)
    with open(ARQ_VERSAO, 'w', encoding='utf-8') as f:
        f.write(sha)
