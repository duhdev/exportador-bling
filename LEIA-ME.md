# Exportador Bling

App web que pega os produtos do Bling, confere cada um pelas regras do marketplace escolhido (Mercado Livre, Shopee, Magalu, Amazon, Americanas, Casas Bahia, Shein ou outro), corrige sozinho o que dá e exporta para a loja conectada no Bling. O que não dá para corrigir sozinho aparece em vermelho, com a explicação, o caminho no Bling e um campo para você digitar o valor certo ali mesmo.

## Como usar (Windows)
1. Instale o Python (https://www.python.org/downloads/) e marque **Add python.exe to PATH** na instalação.
2. Dê dois cliques em **iniciar.bat**. O navegador abre em `http://localhost:8766`. Deixe a janela preta aberta enquanto usa.
3. Para conhecer a tela sem mexer no seu Bling, clique em **Testar com produtos de exemplo**.
4. Para usar com o seu Bling, siga os 4 passos da tela **Conectar ao Bling** (criar o aplicativo na Área do integrador, colar o link de redirecionamento, marcar os escopos e colar Client ID e Client Secret).

Mac/Linux: rode `python3 servidor.py` dentro da pasta.

## Atualização automática
Você só baixa uma vez. Toda vez que abre, o exportador confere no GitHub se tem versão nova e se atualiza sozinho. Com ele aberto, a cada 3 minutos ele confere de novo. Quando tem novidade, aparece o botão **Nova versão: atualizar agora** no topo da tela, e um clique atualiza e recarrega a página. A sua conexão com o Bling (pasta `dados`) é mantida.

## Como funciona
1. **Para onde exportar?** Lista as lojas (canais de venda) do seu Bling e escolhe as regras pelo tipo da loja.
2. **Quais produtos?** Busque e marque os produtos.
3. **Verificar e exportar.** Cada produto ganha um selo: PRONTO, PRONTO COM AVISOS, PRECISA CORRIGIR, ENVIADO ou BLOQUEADO.

Correções automáticas (salvas no produto do Bling, com o antes e depois na tela):
- Título: corta no limite do marketplace sem quebrar palavra, tira emojis, MAIÚSCULAS, "frete grátis", "promoção" e outras palavras proibidas.
- Descrição: tira HTML onde não é aceito, tira telefone, WhatsApp, e-mail e links, completa descrição curta demais com os dados do produto.
- Peso bruto ou líquido vazio (copia um do outro), SKU vazio, GTIN com traços, condição vazia (marca como Novo), marca vazia (usa a marca padrão das Configurações).

Problemas que precisam de você (com campo para corrigir na hora): GTIN inválido ou ausente, marca, peso, medidas da embalagem, imagem, preço abaixo do mínimo e descrição. Se o marketplace recusar no envio, a mensagem do Bling é traduzida e mostra onde corrigir.

## Regras dos marketplaces
Ficam em **regras.json**. Abra no Bloco de Notas para mudar limites (ex.: tamanho do título), palavras proibidas ou se GTIN/marca são obrigatórios. Para outro marketplace, copie um bloco e mude o nome e o `tipos_bling` (o tipo que aparece na loja no Bling). Os valores atuais são um ponto de partida: confira no painel de cada marketplace, porque eles mudam.

## O que é chamado na API v3 do Bling
- OAuth2: `/oauth/authorize` e `/oauth/token` (renova o token sozinho).
- `GET /canais-venda`, `GET /produtos`, `GET /produtos/{id}`, `GET /estoques/saldos`.
- `PUT /produtos/{id}`: grava as correções no produto.
- `GET/POST/PUT /produtos/lojas`: cria ou atualiza o vínculo do produto com a loja, com o preço da loja.
- Respeita o limite do Bling (3 requisições por segundo) e tenta de novo quando o Bling pede para esperar.

## Antes de usar em tudo
- Teste primeiro com **um produto só** e confira no Bling e no marketplace.
- O `PUT /produtos/{id}` regrava o produto inteiro com os dados lidos do Bling mais as correções. Produtos com variações ou kits merecem um teste à parte.
- Dependendo do marketplace, o Bling publica o anúncio a partir do vínculo produto-loja, ou ainda pede para enviar pela tela de anúncios do próprio Bling (categoria e atributos do marketplace). Isso precisa ser confirmado com a sua conta.

A conexão (token) fica só no seu computador, na pasta `dados`. Não compartilhe essa pasta.
