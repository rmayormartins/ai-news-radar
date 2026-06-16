# AI RADAR

Monitor de noticias de IA focado em **sinal sobre ruido**: modelos, pesquisa e o que os
laboratorios andam fazendo, com uma faixa dedicada a **IA na China**. Pagina unica, estatica,
servida pelo GitHub Pages. A coleta roda sozinha via GitHub Actions.

Sem framework, sem build, sem Vercel. So `index.html` + um JSON gerado por um script Python.

## Como funciona

```
GitHub Actions (cron 6/6h)
        |
        v
scripts/fetch_news.py  ->  le feeds RSS, pontua relevancia, classifica, deduplica
        |
        v
data/news.json  (commitado no repo)
        |
        v
index.html  (fetch do JSON, renderiza no navegador)  ->  GitHub Pages
```

A coleta acontece no servidor (Action), entao nao ha problema de CORS: a pagina so le um
arquivo JSON do proprio repositorio.

## Estrutura

```
index.html                       frontend (single-file, zero dependencia)
data/news.json                   dados gerados (seed inicial incluso)
scripts/fetch_news.py            coletor e curador
.github/workflows/update-news.yml  automacao (cron + manual)
```

## Publicar (GitHub Pages)

1. Suba os arquivos para um repositorio (ex: `ai-radar`), branch `main`.
2. **Settings -> Pages -> Build and deployment -> Source: Deploy from a branch**,
   branch `main`, pasta `/ (root)`. Salve.
3. **Settings -> Actions -> General -> Workflow permissions:** marque
   **Read and write permissions** (a Action precisa commitar o `news.json`).
4. Aba **Actions -> update-news -> Run workflow** para fazer a primeira coleta real
   (ou espere o cron). A pagina sai em `https://SEU_USUARIO.github.io/ai-radar/`.

Ate a primeira coleta, a pagina mostra um seed pequeno e um aviso para rodar o workflow.

## Faixas (abas)

- **Todas:** tudo que passou no filtro de relevancia.
- **Modelos:** releases, lancamentos, pesos abertos, APIs.
- **Pesquisa:** papers, metodos, arquiteturas, benchmarks.
- **IA na China:** itens de origem chinesa (fontes chinesas + deteccao por palavra-chave).

Cada card tras um medidor **SNR** (relevancia estimada de 0 a 100). Da pra buscar por texto
(modelo, lab, tema), filtrar por fonte e ordenar por recencia ou relevancia.

## Filtro de relevancia (o "sinal sobre ruido")

`fetch_news.py` pontua cada item por palavras-chave (nomes de modelo, termos de release e de
pesquisa) e penaliza ruido (acoes, processos, ofertas, fofoca de CEO). Feeds amplos
(imprensa) so entram se cruzarem o limiar; blogs de lab entram direto. Assim voce nao recebe
"qualquer noticia de IA a toa".

## Customizar

**Fontes:** edite a lista `SOURCES` no topo de `scripts/fetch_news.py`. Cada fonte tem:

- `region`: `"global"` ou `"china"`
- `weight`: peso da fonte na relevancia (lab/pesquisa valem mais)
- `strict`: se `True`, so entra item acima do limiar (use em feeds amplos)
- `cap`: maximo de itens por fonte por rodada

**Limiares e lexico:** ajuste `MODEL_NAMES`, `RESEARCH_TERMS`, `NOISE_TERMS`, `CHINA_HINTS`
e os cortes de relevancia (`relevance < 40` para strict, `< 20` geral) na funcao de filtro.

**Frequencia:** mude o `cron` em `.github/workflows/update-news.yml`.

## Rodar local

```bash
pip install feedparser
python scripts/fetch_news.py        # gera data/news.json
python -m http.server 8000          # abra http://localhost:8000
```

Abrir o `index.html` direto pelo `file://` funciona com o seed embutido, mas para ler o
`news.json` o navegador exige um servidor (qualquer um serve).

## Fontes incluidas

Global: OpenAI, Google AI/DeepMind, Hugging Face, Ahead of AI, The Gradient, BAIR,
arXiv (cs.AI, cs.LG, cs.CL), MarkTechPost, MIT Tech Review, Last Week in AI, The Verge.

China: Synced (机器之心), Pandaily, TechNode, KrASIA/36Kr, ChinAI (Jeff Ding).

Feeds que saem do ar sao ignorados sem quebrar a coleta (veja `sources` no `news.json` para
o status de cada um na ultima rodada).

## Licenca

MIT.
