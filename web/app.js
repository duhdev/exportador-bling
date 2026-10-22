// Tela do Exportador Bling: escolhe a loja, os produtos, verifica pelas regras do marketplace e exporta.
const $ = (s) => document.querySelector(s);
const estado = { info: null, loja: null, marketplace: null, produtos: [], selecionados: new Set(), pagina: 1, resultados: {} };

async function api(rota, dados) {
  const r = await fetch(rota, dados ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(dados) } : {});
  const j = await r.json().catch(() => ({ erro: 'Resposta inválida do servidor' }));
  if (!r.ok) throw j;
  return j;
}

function textoErro(e) {
  if (e && e.detalhes) return e.detalhes.map((d) => d.mensagem + (d.onde_no_bling ? ` (${d.onde_no_bling})` : '')).join(' ');
  return (e && e.erro) || String(e);
}

function el(tag, attrs = {}, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') n.className = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const f of filhos.flat()) if (f != null) n.append(f);
  return n;
}

// ---------- conexão ----------
async function iniciar() {
  const info = (estado.info = await api('/api/estado'));
  $('#callback').textContent = info.callback;
  $('#clientId').value = info.client_id;
  $('#marcaPadrao').value = info.marca_padrao;
  $('#btnDesconectar').hidden = !info.conectado || info.demo;
  $('#versao').textContent = info.versao ? `versão ${info.versao}` : '';
  $('#btnAtualizar').hidden = !info.atualizacao;
  const pill = $('#conexao');
  pill.textContent = info.demo ? 'Modo demonstração' : info.conectado ? 'Conectado ao Bling' : 'Não conectado';
  pill.className = 'pill ' + (info.conectado ? 'ok' : 'er');

  const sel = $('#regra');
  sel.innerHTML = '';
  for (const [k, m] of Object.entries(info.marketplaces)) sel.append(el('option', { value: k }, m.nome));

  const params = new URLSearchParams(location.search);
  const erro = params.get('erro');
  const pronto = info.conectado && !erro;
  $('#telaConfig').hidden = pronto;
  if (erro) alertar(erro === 'configure' ? 'Falta o Client Secret. Cole o Client ID e o Client Secret do aplicativo do Bling e clique em "Salvar e conectar ao Bling" de novo.' : erro);
  mostrarDiagnostico(info);
  if (params.get('conectado')) avisar('Conectado ao Bling! Agora escolha a loja no passo 1.');
  history.replaceState(null, '', '/');

  for (const s of ['#telaLojas', '#telaProdutos', '#telaEnviar']) $(s).hidden = !pronto;
  if (pronto) { await carregarLojas(); await carregarProdutos(true); }
}

// Quando a pessoa foi mandada ao Bling e ele não voltou para cá, explica o porquê.
function mostrarDiagnostico(info) {
  const box = $('#diagnostico');
  const c = info.conexao || {};
  const recente = c.quando && Date.now() / 1000 - c.quando < 3600;
  box.hidden = info.conectado || !recente || c.etapa !== 'foi_ao_bling';
  if (box.hidden) return;
  box.innerHTML = '';
  box.append(
    el('b', {}, 'Você foi mandado para o Bling, mas o Bling não voltou para cá. Confira estes 3 pontos:'),
    el('ol', {},
      el('li', {}, el('b', {}, 'Login: '), 'se o Bling pediu para entrar na conta, depois ele abre a página inicial dele e esquece a autorização. ',
        'Entre no Bling neste navegador primeiro, volte aqui e clique em "Salvar e conectar ao Bling" de novo.'),
      el('li', {}, el('b', {}, 'Link de redirecionamento: '), 'no aplicativo do Bling ele precisa ser exatamente ',
        el('code', {}, info.callback), ' (com http, sem "s", e sem espaço). Se o Bling te mandou para o Google ou outro site, é isso: use também a opção logo abaixo.'),
      el('li', {}, el('b', {}, 'Aplicativo salvo: '), 'confira se o aplicativo foi salvo no Bling e se o Client ID colado aqui é o dele.')),
    el('div', { class: 'acoes' },
      el('a', { href: 'https://www.bling.com.br/login', target: '_blank', rel: 'noopener' }, el('button', { class: 'sec' }, '1. Entrar no Bling')),
      el('button', { onclick: () => { location.href = '/auth/login'; } }, '2. Tentar conectar de novo')));
}

// Aviso que fica na tela até a pessoa fechar (some sozinho só quando é boa notícia).
function alertar(msg, tipo = 'erro') {
  const box = el('div', { class: `card item ${tipo} aviso-topo` }, el('span', {}, msg),
    el('button', { class: 'mini sec', onclick: () => box.remove() }, 'Fechar'));
  $('main').prepend(box);
  box.scrollIntoView({ behavior: 'smooth', block: 'center' });
  return box;
}
function avisar(msg) {
  const box = alertar(msg, 'fix');
  setTimeout(() => box.remove(), 8000);
}

$('#btnConfig').onclick = () => { $('#telaConfig').hidden = !$('#telaConfig').hidden; };
$('#copiarCallback').onclick = () => navigator.clipboard.writeText($('#callback').textContent);
$('#btnConectar').onclick = async () => {
  const dados = { client_id: $('#clientId').value.trim(), marca_padrao: $('#marcaPadrao').value.trim(), demo: false };
  if ($('#clientSecret').value.trim()) dados.client_secret = $('#clientSecret').value.trim();
  if (!dados.client_id) return alertar('Cole o Client ID do aplicativo do Bling (passo 4 acima).');
  if (!dados.client_secret && !estado.info.configurado) return alertar('Cole também o Client Secret do aplicativo do Bling (passo 4 acima).');
  await api('/api/config', dados);
  location.href = '/auth/login';
};
$('#btnDemo').onclick = async () => {
  await api('/api/config', { demo: true, marca_padrao: $('#marcaPadrao').value.trim() });
  location.reload();
};
$('#btnColar').onclick = async () => {
  const url = $('#urlColada').value.trim();
  if (!url) return alertar('Cole o endereço da página para onde o Bling te mandou.');
  try {
    await api('/api/colar-retorno', { url });
    location.href = '/?conectado=1';
  } catch (e) { alertar(textoErro(e)); }
};
$('#btnDesconectar').onclick = async () => { await api('/api/desconectar', {}); location.reload(); };

// ---------- passo 1: lojas ----------
async function carregarLojas() {
  const box = $('#lojas');
  box.textContent = 'Carregando lojas…';
  try {
    const { canais } = await api('/api/canais');
    box.innerHTML = '';
    if (!canais.length) box.textContent = 'Nenhuma loja encontrada no Bling. Conecte um marketplace em Preferências › Integrações.';
    for (const c of canais) {
      const nomeMk = estado.info.marketplaces[c.marketplace].nome;
      const b = el('button', { class: 'loja', onclick: () => escolherLoja(c, b) }, c.nome, el('small', {}, `${c.tipo} · regras: ${nomeMk}`));
      box.append(b);
    }
  } catch (e) { box.textContent = 'Não consegui listar as lojas: ' + textoErro(e); }
}

function escolherLoja(c, botao) {
  estado.loja = c;
  estado.marketplace = c.marketplace;
  $('#regra').value = c.marketplace;
  document.querySelectorAll('.loja').forEach((b) => b.classList.toggle('sel', b === botao));
}
$('#regra').onchange = (e) => { estado.marketplace = e.target.value; };

// ---------- passo 2: produtos ----------
async function carregarProdutos(reset) {
  if (reset) { estado.pagina = 1; estado.produtos = []; }
  const lista = $('#produtos');
  try {
    const { produtos } = await api(`/api/produtos?pagina=${estado.pagina}&pesquisa=${encodeURIComponent($('#pesquisa').value)}`);
    estado.produtos.push(...produtos);
    $('#maisProdutos').hidden = produtos.length < 50;
  } catch (e) { lista.textContent = 'Não consegui listar os produtos: ' + textoErro(e); return; }
  desenharProdutos();
}

function desenharProdutos() {
  const lista = $('#produtos');
  lista.innerHTML = '';
  if (!estado.produtos.length) lista.append(el('div', { class: 'prod muted' }, 'Nenhum produto encontrado.'));
  for (const p of estado.produtos) {
    const cb = el('input', { type: 'checkbox' });
    cb.checked = estado.selecionados.has(p.id);
    cb.onchange = () => { cb.checked ? estado.selecionados.add(p.id) : estado.selecionados.delete(p.id); contar(); };
    const linha = el('label', { class: 'prod' }, cb, el('span', { class: 'n' }, p.nome),
      el('span', { class: 'c' }, `${p.codigo || 'sem SKU'} · R$ ${Number(p.preco || 0).toFixed(2)}`));
    lista.append(linha);
  }
  contar();
}

function contar() {
  $('#contagem').textContent = `${estado.selecionados.size} selecionado(s)`;
}

let tempoBusca;
$('#pesquisa').oninput = () => { clearTimeout(tempoBusca); tempoBusca = setTimeout(() => carregarProdutos(true), 400); };
$('#maisProdutos').onclick = () => { estado.pagina++; carregarProdutos(false); };
$('#todos').onchange = (e) => {
  for (const p of estado.produtos) e.target.checked ? estado.selecionados.add(p.id) : estado.selecionados.delete(p.id);
  desenharProdutos();
};

// ---------- passo 3: verificar e exportar ----------
async function processar(exportar) {
  if (!estado.marketplace) return alertar('Escolha a loja no passo 1.');
  if (exportar && !estado.loja) return alertar('Escolha a loja no passo 1.');
  const ids = [...estado.selecionados];
  if (!ids.length) return alertar('Selecione pelo menos um produto no passo 2.');

  const botoes = [$('#btnVerificar'), $('#btnExportar')];
  botoes.forEach((b) => (b.disabled = true));
  $('#resultados').innerHTML = '';
  estado.resultados = {};
  const barra = $('#progresso');
  barra.hidden = false;
  let feitos = 0;

  // duas filas em paralelo: o servidor já respeita o limite de requisições do Bling
  const fila = [...ids];
  const trabalhador = async () => {
    while (fila.length) {
      const id = fila.shift();
      const dados = { id, marketplace: estado.marketplace };
      let r;
      try {
        r = exportar
          ? await api('/api/exportar', { ...dados, loja_id: estado.loja.id, aplicar_correcoes: $('#autoCorrigir').checked, ajuste_preco: Number($('#ajuste').value || 0) })
          : await api('/api/verificar', dados);
      } catch (e) {
        r = { id, resultado: 'falha', mensagem: textoErro(e), problemas: [], correcoes: [] };
      }
      r.nome = r.nome || (estado.produtos.find((p) => p.id === id) || {}).nome || `Produto ${id}`;
      estado.resultados[id] = r;
      desenharResultado(r, exportar);
      feitos++;
      barra.firstElementChild.style.width = `${(feitos / ids.length) * 100}%`;
      resumir();
    }
  };
  await Promise.all([trabalhador(), trabalhador()]);
  botoes.forEach((b) => (b.disabled = false));
}

$('#btnVerificar').onclick = () => processar(false);
$('#btnExportar').onclick = () => processar(true);

function selo(r) {
  if (r.resultado === 'enviado') return ['s-ok', 'ENVIADO'];
  if (r.resultado === 'bloqueado' || r.resultado === 'recusado' || r.resultado === 'falha') return ['s-erro', r.resultado.toUpperCase()];
  if (r.status === 'erro') return ['s-erro', 'PRECISA CORRIGIR'];
  if (r.status === 'aviso') return ['s-aviso', 'PRONTO, COM AVISOS'];
  return ['s-ok', 'PRONTO'];
}

function resumir() {
  const rs = Object.values(estado.resultados);
  const n = (f) => rs.filter(f).length;
  const box = $('#resumo');
  box.innerHTML = '';
  const add = (cls, txt, qtd) => qtd && box.append(el('span', { class: cls }, `${qtd} ${txt}`));
  add('s-ok', 'enviado(s)', n((r) => r.resultado === 'enviado'));
  add('s-ok', 'pronto(s)', n((r) => !r.resultado && r.status !== 'erro'));
  add('s-erro', 'precisa(m) de você', n((r) => ['bloqueado', 'recusado', 'falha'].includes(r.resultado) || (!r.resultado && r.status === 'erro')));
  add('s-fix', 'correção(ões) automática(s)', rs.reduce((t, r) => t + (r.correcoes || []).length, 0));
}

function desenharResultado(r, exportar) {
  const art = $('#tplResultado').content.firstElementChild.cloneNode(true);
  art.dataset.id = r.id;
  const [cls, txt] = selo(r);
  const s = art.querySelector('.selo');
  s.className = 'selo ' + cls;
  s.textContent = txt;
  art.querySelector('.nome').textContent = r.nome;
  art.querySelector('.msg').textContent = r.mensagem || '';
  const corpo = art.querySelector('.corpo');

  for (const c of r.correcoes || []) {
    corpo.append(el('div', { class: 'item fix' },
      el('b', {}, '✔ Corrigido sozinho: '), c.motivo,
      el('div', {}, el('span', { class: 'antes' }, String(c.antes ?? '(vazio)').slice(0, 300)), ' → ', el('span', {}, String(c.depois).slice(0, 300)))));
  }
  for (const d of r.detalhes || []) {
    corpo.append(el('div', { class: 'item erro' }, el('b', {}, 'O marketplace recusou: '), d.mensagem,
      d.onde_no_bling ? el('div', { class: 'onde' }, 'Onde corrigir no Bling: ' + d.onde_no_bling) : null,
      d.original !== d.mensagem ? el('div', { class: 'onde' }, 'Mensagem original: ' + d.original) : null));
  }
  for (const p of r.problemas || []) corpo.append(desenharProblema(p, r, exportar));
  if (!corpo.childElementCount && !r.resultado) corpo.append(el('div', { class: 'muted' }, `Tudo certo para o ${estado.info.marketplaces[estado.marketplace].nome}.`));

  const antigo = document.querySelector(`.resultado[data-id="${r.id}"]`);
  antigo ? antigo.replaceWith(art) : $('#resultados').append(art);
}

function desenharProblema(p, r, exportar) {
  const item = el('div', { class: 'item ' + p.nivel },
    el('b', {}, (p.nivel === 'erro' ? '✖ ' : '⚠ ') + p.mensagem),
    el('div', {}, el('b', {}, 'Como corrigir: '), p.como_corrigir),
    p.onde_no_bling ? el('div', { class: 'onde' }, 'Ou no Bling: ' + p.onde_no_bling) : null);
  if (p.editar) item.append(editor(p, r, exportar));
  return item;
}

// Campo para corrigir ali mesmo: salva no Bling e verifica (ou exporta) de novo.
function editor(p, r, exportar) {
  const box = el('div', { class: 'editor' });
  let ler;
  const t = p.editar.tipo;
  if (t === 'dimensoes') {
    const [l, a, pr] = ['Largura', 'Altura', 'Profund.'].map((x) => el('input', { class: 'dim', type: 'number', step: '0.1', min: '0', placeholder: x + ' cm', title: x + ' em cm' }));
    box.append(l, a, pr);
    ler = () => ({ largura: l.value, altura: a.value, profundidade: pr.value });
  } else if (t === 'textarea') {
    const ta = el('textarea', { placeholder: 'Digite a descrição' });
    box.append(ta);
    ler = () => ta.value;
  } else {
    const ph = { peso: 'Peso em kg (ex.: 0.35)', dinheiro: 'Preço (ex.: 99.90)', numero_texto: 'Somente números', imagem: 'https://… link da imagem' }[t] || 'Digite aqui';
    const inp = el('input', { placeholder: ph, inputmode: ['peso', 'dinheiro', 'numero_texto'].includes(t) ? 'decimal' : 'text' });
    if (p.editar.max) inp.maxLength = p.editar.max;
    box.append(inp);
    ler = () => inp.value;
  }
  const btn = el('button', {}, 'Salvar no Bling');
  btn.onclick = async () => {
    const valor = ler();
    if (typeof valor === 'string' ? !valor.trim() : Object.values(valor).some((v) => !v)) return;
    btn.disabled = true;
    btn.textContent = 'Salvando…';
    try {
      const novo = await api('/api/corrigir-campo', { id: r.id, campo: p.campo, valor, marketplace: estado.marketplace });
      let fim = novo;
      if (exportar && novo.status !== 'erro') {
        fim = await api('/api/exportar', { id: r.id, marketplace: estado.marketplace, loja_id: estado.loja.id, aplicar_correcoes: $('#autoCorrigir').checked, ajuste_preco: Number($('#ajuste').value || 0) });
      }
      fim.nome = fim.nome || r.nome;
      estado.resultados[r.id] = fim;
      desenharResultado(fim, exportar);
      resumir();
    } catch (e) {
      btn.disabled = false;
      btn.textContent = 'Salvar no Bling';
      alertar('Não salvou: ' + textoErro(e));
    }
  };
  box.append(btn);
  return box;
}

// ---------- atualização automática ----------
// o servidor confere o GitHub; quando tem versão nova, aparece o botão no topo
setInterval(async () => {
  try { $('#btnAtualizar').hidden = !(await api('/api/estado')).atualizacao; } catch (e) { /* servidor reiniciando */ }
}, 60000);

$('#btnAtualizar').onclick = async () => {
  const b = $('#btnAtualizar');
  b.disabled = true;
  b.textContent = 'Atualizando…';
  try {
    const r = await api('/api/atualizar', {});
    if (!r.atualizado) { b.hidden = true; return avisar('Você já está na versão mais nova.'); }
  } catch (e) {
    b.disabled = false;
    b.textContent = 'Nova versão: atualizar agora';
    return alertar('Não consegui atualizar: ' + textoErro(e));
  }
  // espera o servidor voltar com a versão nova e recarrega a página
  await new Promise((r) => setTimeout(r, 1500));
  for (let i = 0; i < 40; i++) {
    try { await api('/api/estado'); return location.reload(); } catch (e) { await new Promise((r) => setTimeout(r, 500)); }
  }
  alertar('O exportador não voltou sozinho. Feche a janela preta e abra o iniciar.bat de novo.');
};

iniciar().catch((e) => alertar('Erro ao abrir: ' + textoErro(e)));
