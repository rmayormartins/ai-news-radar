#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Radar - coletor e curador de noticias de IA.

Le uma lista curada de feeds RSS/Atom, pontua relevancia (sinal vs ruido),
classifica cada item (modelo / pesquisa / geral), marca a regiao (global / china),
deduplica e grava data/news.json para o frontend estatico consumir.

Roda no GitHub Actions (cron). Sem dependencias alem de feedparser.
"""

import json
import re
import sys
import time
import html
import hashlib
import datetime as dt
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import feedparser

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "news.json"

# -------------------------------------------------------------------
# FONTES
# region: "global" ou "china"
# weight: multiplicador de relevancia da fonte (labs e pesquisa valem mais)
# strict: se True, so entra item que cruzar o limiar de relevancia
#         (feeds amplos como Verge/SCMP) - feeds de lab entram sempre
# cap:    maximo de itens por fonte nesta rodada
# -------------------------------------------------------------------
SOURCES = [
    # --- Labs e fontes oficiais (global) ---
    {"name": "OpenAI",            "url": "https://openai.com/news/rss.xml",                                    "region": "global", "weight": 1.6, "strict": False, "cap": 12},
    {"name": "Google AI / DeepMind", "url": "https://blog.google/technology/ai/rss/",                          "region": "global", "weight": 1.5, "strict": False, "cap": 12},
    {"name": "Google Research",   "url": "https://research.google/blog/rss/",                                  "region": "global", "weight": 1.4, "strict": False, "cap": 8},
    {"name": "Meta AI",           "url": "https://ai.meta.com/blog/rss/",                                      "region": "global", "weight": 1.4, "strict": False, "cap": 8},
    {"name": "Hugging Face",      "url": "https://huggingface.co/blog/feed.xml",                               "region": "global", "weight": 1.4, "strict": False, "cap": 12},
    {"name": "Ahead of AI",       "url": "https://magazine.sebastianraschka.com/feed",                         "region": "global", "weight": 1.4, "strict": False, "cap": 8},
    {"name": "Simon Willison",    "url": "https://simonwillison.net/atom/everything/",                         "region": "global", "weight": 1.2, "strict": True,  "cap": 6},
    {"name": "The Gradient",      "url": "https://thegradient.pub/rss/",                                       "region": "global", "weight": 1.3, "strict": False, "cap": 8},
    {"name": "BAIR (Berkeley)",   "url": "https://bair.berkeley.edu/blog/feed.xml",                            "region": "global", "weight": 1.4, "strict": False, "cap": 8},
    {"name": "MIT News (IA)",     "url": "https://news.mit.edu/rss/topic/artificial-intelligence2",            "region": "global", "weight": 1.2, "strict": False, "cap": 8},
    {"name": "Apple ML Research", "url": "https://machinelearning.apple.com/rss.xml",                          "region": "global", "weight": 1.3, "strict": False, "cap": 6},
    {"name": "AWS Machine Learning", "url": "https://aws.amazon.com/blogs/machine-learning/feed/",              "region": "global", "weight": 1.0, "strict": True,  "cap": 6},

    # --- Pesquisa primaria (global, alto volume -> strict + cap baixo) ---
    {"name": "arXiv cs.AI",       "url": "https://rss.arxiv.org/rss/cs.AI",                                    "region": "global", "weight": 1.2, "strict": True,  "cap": 8},
    {"name": "arXiv cs.LG",       "url": "https://rss.arxiv.org/rss/cs.LG",                                    "region": "global", "weight": 1.2, "strict": True,  "cap": 8},
    {"name": "arXiv cs.CL",       "url": "https://rss.arxiv.org/rss/cs.CL",                                    "region": "global", "weight": 1.2, "strict": True,  "cap": 8},
    {"name": "arXiv cs.CV",       "url": "https://rss.arxiv.org/rss/cs.CV",                                    "region": "global", "weight": 1.2, "strict": True,  "cap": 6},
    {"name": "arXiv cs.RO",       "url": "https://rss.arxiv.org/rss/cs.RO",                                    "region": "global", "weight": 1.0, "strict": True,  "cap": 5},

    # --- Imprensa / analise (global) ---
    {"name": "MarkTechPost",      "url": "https://www.marktechpost.com/feed/",                                 "region": "global", "weight": 1.1, "strict": True,  "cap": 12},
    {"name": "The Decoder",       "url": "https://the-decoder.com/feed/",                                      "region": "global", "weight": 1.2, "strict": False, "cap": 10},
    {"name": "MIT Tech Review",   "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed/", "region": "global", "weight": 1.1, "strict": True,  "cap": 10},
    {"name": "VentureBeat AI",    "url": "https://venturebeat.com/category/ai/feed/",                          "region": "global", "weight": 1.0, "strict": True,  "cap": 10},
    {"name": "IEEE Spectrum",     "url": "https://spectrum.ieee.org/feeds/feed.rss",                           "region": "global", "weight": 1.0, "strict": True,  "cap": 6},
    {"name": "KDnuggets",         "url": "https://www.kdnuggets.com/feed",                                     "region": "global", "weight": 1.0, "strict": True,  "cap": 6},
    {"name": "TechXplore (IA/ML)", "url": "https://techxplore.com/rss-feed/machine-learning-ai-news/",         "region": "global", "weight": 1.0, "strict": True,  "cap": 6},
    {"name": "Last Week in AI",   "url": "https://lastweekin.ai/feed",                                         "region": "global", "weight": 1.1, "strict": False, "cap": 6},
    {"name": "TechCrunch",        "url": "https://techcrunch.com/feed/",                                       "region": "global", "weight": 0.9, "strict": True,  "cap": 8},
    {"name": "Ars Technica",      "url": "https://feeds.arstechnica.com/arstechnica/index",                    "region": "global", "weight": 0.9, "strict": True,  "cap": 6},
    {"name": "The Verge AI",      "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",  "region": "global", "weight": 0.9, "strict": True,  "cap": 10},
    {"name": "Wired AI",          "url": "https://www.wired.com/feed/tag/ai/latest/rss",                       "region": "global", "weight": 0.9, "strict": True,  "cap": 8},
    {"name": "Analytics India",   "url": "https://analyticsindiamag.com/feed/",                                "region": "global", "weight": 0.9, "strict": True,  "cap": 6},

    # --- Analise / newsletters (global) ---
    {"name": "Interconnects",     "url": "https://www.interconnects.ai/feed",                                  "region": "global", "weight": 1.3, "strict": False, "cap": 6},
    {"name": "The Algorithmic Bridge", "url": "https://www.thealgorithmicbridge.com/feed",                     "region": "global", "weight": 1.1, "strict": True,  "cap": 6},
    {"name": "One Useful Thing",  "url": "https://www.oneusefulthing.org/feed",                                "region": "global", "weight": 1.1, "strict": True,  "cap": 5},
    {"name": "Don't Worry About the Vase", "url": "https://thezvi.substack.com/feed",                          "region": "global", "weight": 1.1, "strict": True,  "cap": 5},

    # --- IA na China (foco do pedido) ---
    {"name": "Synced (机器之心)",  "url": "https://syncedreview.com/feed/",                                     "region": "china",  "weight": 1.5, "strict": False, "cap": 12},
    {"name": "ChinAI (Jeff Ding)", "url": "https://chinai.substack.com/feed",                                  "region": "china",  "weight": 1.4, "strict": False, "cap": 6},
    {"name": "Recode China AI",   "url": "https://recodechinaai.substack.com/feed",                            "region": "china",  "weight": 1.4, "strict": False, "cap": 8},
    {"name": "Pandaily",          "url": "https://pandaily.com/feed/",                                         "region": "china",  "weight": 1.2, "strict": True,  "cap": 10},
    {"name": "TechNode",          "url": "https://technode.com/feed/",                                         "region": "china",  "weight": 1.1, "strict": True,  "cap": 10},
    {"name": "KrASIA / 36Kr",     "url": "https://kr-asia.com/feed",                                           "region": "china",  "weight": 1.1, "strict": True,  "cap": 10},
    {"name": "SCMP Tech",         "url": "https://www.scmp.com/rss/36/feed",                                   "region": "china",  "weight": 1.0, "strict": True,  "cap": 8},
    {"name": "SCMP Big Tech",     "url": "https://www.scmp.com/rss/320663/feed",                               "region": "china",  "weight": 1.1, "strict": True,  "cap": 10},
    {"name": "ChinaTalk",         "url": "https://www.chinatalk.media/feed",                                   "region": "china",  "weight": 1.1, "strict": True,  "cap": 6},
    {"name": "AI China News",     "url": "https://aichina.news/feed/",                                         "region": "china",  "weight": 1.2, "strict": True,  "cap": 10},
    {"name": "The China Academy", "url": "https://thechinaacademy.org/feed/",                                  "region": "china",  "weight": 1.0, "strict": True,  "cap": 6},
    {"name": "China Internet Watch", "url": "https://www.chinainternetwatch.com/feed/",                         "region": "china",  "weight": 0.95, "strict": True, "cap": 6},
    {"name": "CnTechPost",        "url": "https://cntechpost.com/feed/",                                       "region": "china",  "weight": 1.0, "strict": True,  "cap": 8},
    {"name": "Sixth Tone",        "url": "https://www.sixthtone.com/rss",                                      "region": "china",  "weight": 1.0, "strict": True,  "cap": 6},
    {"name": "Caixin Global",     "url": "https://www.caixinglobal.com/feed/",                                 "region": "china",  "weight": 1.0, "strict": True,  "cap": 6},
]

# -------------------------------------------------------------------
# LEXICO DE RELEVANCIA
# -------------------------------------------------------------------
MODEL_NAMES = [
    "gpt", "o1", "o3", "o4", "chatgpt", "claude", "gemini", "llama", "mistral",
    "mixtral", "qwen", "deepseek", "ernie", "kimi", "moonshot", "glm", "yi ",
    "phi-", "grok", "command r", "dbrx", "gemma", "falcon", "stable diffusion",
    "sora", "veo", "flux", "nemotron", "minimax", "hunyuan", "doubao", "step-",
    "internlm", "baichuan", "skywork",
]
MODEL_TERMS = [
    "model", "modelo", "release", "launch", "introducing", "open-source",
    "open source", "open-weight", "open weights", "weights", "checkpoint",
    "fine-tune", "fine-tuning", "available now", "now available", "api",
    "multimodal", "context window", "tokens", "inference", "quantiz",
    "distill", "moe", "mixture of experts",
]
RESEARCH_TERMS = [
    "research", "pesquisa", "paper", "arxiv", "study", "we present", "we propose",
    "we introduce", "method", "approach", "architecture", "training", "pretrain",
    "scaling", "scaling law", "evaluation", "benchmark", "alignment",
    "interpretability", "reasoning", "reinforcement learning", "rlhf", "rl ",
    "transformer", "attention", "diffusion", "fine-grained", "state-of-the-art",
    "sota", "agent", "agentic", "embedding", "retrieval", "rag",
]
SIGNAL_TERMS = MODEL_NAMES + MODEL_TERMS + RESEARCH_TERMS + [
    "ai", "a.i.", "artificial intelligence", "machine learning", "deep learning",
    "neural", "llm", "large language model", "foundation model", "generative",
    "openai", "anthropic", "deepmind", "google", "meta", "nvidia", "microsoft",
    "alibaba", "tencent", "baidu", "bytedance", "huawei", "zhipu", "01.ai",
    "robot", "autonomous", "compute", "gpu", "dataset", "lab",
]
# ruido: itens predominantemente sobre isto perdem pontos
NOISE_TERMS = [
    "stock", "share price", "shares", "ipo", "earnings", "lawsuit", "sued",
    "settlement", "deal", "acquire", "acquisition", "funding round", "valuation",
    "ceo", "hire", "layoff", "crypto", "bitcoin", "gadget review", "deals",
    "discount", "coupon", "best laptop", "how to use chatgpt", "prompt",
]
CHINA_HINTS = [
    "china", "chinese", "beijing", "shanghai", "shenzhen", "hangzhou",
    "alibaba", "tencent", "baidu", "bytedance", "huawei", "deepseek", "qwen",
    "zhipu", "moonshot", "kimi", "ernie", "hunyuan", "doubao", "minimax",
    "01.ai", "01 ai", "yi ", "internlm", "baichuan", "stepfun", "step-",
    "sensetime", "iflytek", "cambricon", "biren", "moore threads",
]

WORD_RE = re.compile(r"[a-z0-9\.\-]+")


def norm(s):
    return (s or "").strip()


def clean_text(s, limit=320):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)          # tira tags
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + "..."
    return s


def count_hits(text, terms):
    return sum(1 for t in terms if t in text)


def score_item(title, summary, src):
    """Retorna (relevancia 0-100, categoria, eh_china)."""
    blob = (title + " " + summary).lower()

    signal = count_hits(blob, SIGNAL_TERMS)
    model_hits = count_hits(blob, MODEL_NAMES) * 2 + count_hits(blob, MODEL_TERMS)
    research_hits = count_hits(blob, RESEARCH_TERMS)
    noise = count_hits(blob, NOISE_TERMS)

    raw = signal * 4 + model_hits * 5 + research_hits * 4 - noise * 6
    raw = raw * src["weight"]
    # titulo carrega mais peso: nomes de modelo no titulo dao bonus
    if count_hits(title.lower(), MODEL_NAMES):
        raw += 14
    # curva saturante: da boa variacao no medidor sem todo mundo bater 100
    relevance = 0 if raw <= 0 else int(round(100 * raw / (raw + 35.0)))

    if model_hits >= research_hits and model_hits > 0:
        category = "modelo"
    elif research_hits > 0:
        category = "pesquisa"
    else:
        category = "geral"

    is_china = src["region"] == "china" or count_hits(blob, CHINA_HINTS) >= 1
    return relevance, category, is_china


def parse_date(entry):
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            try:
                return dt.datetime.fromtimestamp(time.mktime(val), tz=dt.timezone.utc)
            except Exception:
                pass
    return None


def fetch(url, timeout=25):
    """Baixa o feed com User-Agent (alguns servidores bloqueiam o default)."""
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; AI-Radar/1.0; +github-pages)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def main():
    now = dt.datetime.now(dt.timezone.utc)
    horizon = now - dt.timedelta(days=45)
    items = []
    seen = set()
    report = []

    for src in SOURCES:
        ok, kept = 0, 0
        try:
            raw = fetch(src["url"])
            feed = feedparser.parse(raw)
            entries = feed.entries or []
            ok = len(entries)
        except (URLError, HTTPError, Exception) as e:
            report.append({"source": src["name"], "status": f"ERRO: {e}", "kept": 0})
            print(f"[!] {src['name']}: {e}", file=sys.stderr)
            continue

        per_src = []
        for e in entries:
            title = clean_text(e.get("title", ""), 240)
            link = norm(e.get("link", ""))
            if not title or not link:
                continue

            key = hashlib.md5(re.sub(r"[^a-z0-9]", "", title.lower()).encode()).hexdigest()
            if key in seen:
                continue

            summary = clean_text(e.get("summary", "") or e.get("description", ""))
            date = parse_date(e)
            if date and date < horizon:
                continue

            relevance, category, is_china = score_item(title, summary, src)

            # filtro de "noticia a toa": fontes amplas precisam cruzar o limiar
            if src["strict"] and relevance < 40:
                continue
            if relevance < 20:
                continue

            seen.add(key)
            per_src.append({
                "title": title,
                "link": link,
                "summary": summary,
                "source": src["name"],
                "region": "china" if is_china else "global",
                "category": category,
                "relevance": relevance,
                "date": date.isoformat() if date else None,
                "ts": date.timestamp() if date else 0,
            })

        # ordena por relevancia dentro da fonte e aplica o cap
        per_src.sort(key=lambda x: (x["relevance"], x["ts"]), reverse=True)
        per_src = per_src[: src["cap"]]
        kept = len(per_src)
        items.extend(per_src)
        report.append({"source": src["name"], "status": f"ok ({ok} itens)", "kept": kept})
        print(f"[+] {src['name']}: {ok} lidos, {kept} mantidos")

    # ordenacao final: mais recentes e relevantes no topo
    items.sort(key=lambda x: (x["ts"], x["relevance"]), reverse=True)
    items = items[:260]

    payload = {
        "generated_at": now.isoformat(),
        "count": len(items),
        "china_count": sum(1 for i in items if i["region"] == "china"),
        "sources": report,
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK -> {OUT} ({len(items)} itens, {payload['china_count']} da China)")


if __name__ == "__main__":
    main()
