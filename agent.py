#!/usr/bin/env python3
"""
SEO Morning Post Agent
Ogni mattina analizza SearchHerald, seleziona 2 notizie SEO/AI rilevanti
e genera 2 post LinkedIn separati (uno per articolo) via email.
"""

import os
import re
import json
import time
import smtplib
import logging
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# CONFIGURAZIONE
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
EMAIL_FROM        = os.getenv("EMAIL_FROM",        "agent@tuodominio.com")
EMAIL_TO          = os.getenv("EMAIL_TO",          "carmine@eskimoz.it")
SMTP_HOST         = os.getenv("SMTP_HOST",         "smtp.gmail.com")
SMTP_PORT         = int(os.getenv("SMTP_PORT",     "587"))
SMTP_USER         = os.getenv("SMTP_USER",         "agent@tuodominio.com")
SMTP_PASS         = os.getenv("SMTP_PASS",         "")

SOURCE_URL = "https://searchherald.com/"
LOG_FILE   = "logs/seo_agent.log"
MODEL      = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1200

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FUNZIONI
# ---------------------------------------------------------------------------

def fetch_headlines(url: str) -> list[dict]:
    """Scarica i titoli dal SearchHerald."""
    log.info("Recupero titoli da %s", url)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SEOAgent/1.0)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    headlines = []
    seen = set()
    for tag in soup.select("h2 a, h3 a"):
        title = tag.get_text(strip=True)
        href  = tag.get("href", "")
        if (
            len(title) > 25
            and href.startswith("http")
            and "searchherald.com/topic" not in href
            and "searchherald.com/archive" not in href
            and href not in seen
        ):
            headlines.append({"title": title, "url": href})
            seen.add(href)

    log.info("Trovati %d titoli", len(headlines))
    return headlines[:25]


def fetch_article_text(url: str, max_chars: int = 2000) -> str:
    """Scarica il testo principale di un articolo."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SEOAgent/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["nav", "header", "footer", "aside", "script", "style"]):
            tag.decompose()
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text()) > 60]
        text = " ".join(paragraphs)
        return text[:max_chars]
    except Exception as e:
        log.warning("Impossibile leggere %s: %s", url, e)
        return ""


def call_claude(system: str, user: str, retries: int = 4) -> str:
    """Chiama l'API Anthropic con retry automatico in caso di sovraccarico (529)."""
    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}]
    }
    for attempt in range(retries):
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json=payload,
            timeout=60
        )
        if resp.status_code == 529:
            wait = 15 * (attempt + 1)  # 15s, 30s, 45s, 60s
            log.warning("API sovraccarica (529), tentativo %d/%d — attendo %ds...", attempt + 1, retries, wait)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    raise RuntimeError(f"API Anthropic non disponibile dopo {retries} tentativi (529).")


def select_articles(headlines: list[dict]) -> list[dict]:
    """Usa Claude per selezionare gli 8 candidati più rilevanti."""
    log.info("Selezione articoli con Claude...")
    system = (
        "Sei un esperto SEO e AI strategist. Analizza questi titoli di notizie SEO/AI "
        "e seleziona gli 8 più rilevanti e attuali per un professionista SEO italiano nel 2026. "
        "Preferisci: aggiornamenti algoritmo Google, AI Overview, LLM search, AEO, GEO, "
        "studi su organic traffic, AI agents. Evita notizie su Google Ads o Merchant Center. "
        "Rispondi SOLO con JSON valido, zero testo fuori dal JSON:\n"
        '{"selected": [{"index": 0, "title": "...", "url": "...", "why": "..."}]}'
    )
    headlines_text = "\n".join(f"{i}. {h['title']}" for i, h in enumerate(headlines))
    raw = call_claude(system, headlines_text)
    clean = re.sub(r"```json|```", "", raw).strip()
    data = json.loads(clean)
    selected = []
    for item in data.get("selected", [])[:8]:
        idx = item.get("index", 0)
        selected.append({
            "title": item.get("title") or headlines[idx]["title"],
            "url":   item.get("url")   or headlines[idx]["url"],
            "why":   item.get("why", "")
        })
    log.info("Selezionati %d candidati", len(selected))
    return selected


def pick_readable_articles(candidates: list[dict], needed: int = 2) -> list[dict]:
    """Scorre i candidati e restituisce i primi N con testo leggibile."""
    readable = []
    for art in candidates:
        if len(readable) >= needed:
            break
        log.info("Verifico leggibilità: %s", art["url"])
        text = fetch_article_text(art["url"])
        if text and len(text) > 100:
            art["text"] = text
            readable.append(art)
            log.info("✅ Leggibile (%d chars): %s", len(text), art["title"][:60])
        else:
            log.warning("🚫 Bloccato o vuoto (%d chars), salto: %s", len(text) if text else 0, art["title"][:60])

    log.info("Articoli leggibili trovati: %d / %d richiesti", len(readable), needed)

    if not readable:
        raise ValueError("Nessun articolo leggibile trovato tra i candidati.")

    return readable


def generate_post(article: dict) -> str:
    """Genera UN post LinkedIn per un singolo articolo."""
    log.info("Generazione post per: %s", article["title"][:60])
    content = f"=== {article['title']} ===\n{article['text']}"

    system = (
        "Sei Carmine, Client & SEO Director di Eskimoz, agenzia SEO italiana. "
        "Scrivi UN post LinkedIn in italiano basato sulla notizia qui sotto.\n\n"
        "STILE OBBLIGATORIO:\n"
        "- Tono diretto, concreto, autorevole ma non accademico\n"
        "- Emoji come marcatori strutturali (parsimonia, max 4-5 nel post)\n"
        "- Bullet point sintetici per i punti chiave\n"
        "- **Bold** solo su dati e concetti chiave\n"
        "- Dati e numeri dove disponibili\n"
        "- Chiusura con domanda o CTA engagement\n"
        "- CTA finale: 'Seguimi per restare aggiornato su SEO e AI search 👇'\n"
        "- Hashtag finali: #SEO #AISearch #AEO #SearchMarketing\n"
        "- NO frasi da chatbot (Nel mondo di oggi..., È fondamentale...)\n"
        "- NO citazione esplicita della fonte\n"
        "- Lunghezza: 200-280 parole\n\n"
        "Scrivi solo il testo del post, senza note o spiegazioni."
    )
    post = call_claude(system, content)
    log.info("Post generato (%d caratteri)", len(post))
    return post


def send_email(posts_data: list[dict]) -> None:
    """Invia tutti i post via email — uno per articolo."""
    log.info("Invio email a %s...", EMAIL_TO)
    today = datetime.now().strftime("%d %B %Y")

    def format_post_block(art: dict, post: str, num: int) -> str:
        post_html = post.replace("\n", "<br>")
        post_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", post_html)
        return f"""
        <div style="margin-bottom:32px;">
          <p style="font-size:12px;color:#888;margin:0 0 6px;font-weight:600;
             text-transform:uppercase;letter-spacing:.05em;">📝 Post #{num}</p>
          <div style="background:#f7f9fb;border-left:3px solid #0a66c2;
             padding:16px 20px;border-radius:0 6px 6px 0;font-size:14px;line-height:1.75;">
            {post_html}
          </div>
          <div style="margin-top:10px;padding:12px;background:#f0f4ff;border-radius:6px;">
            <p style="font-size:11px;color:#888;margin:0 0 6px;font-weight:600;
               text-transform:uppercase;letter-spacing:.05em;">📚 Fonte</p>
            <a href="{art['url']}" style="color:#0a66c2;font-size:13px;
               text-decoration:none;" target="_blank">🔗 {art['title']}</a>
          </div>
        </div>
        """

    blocks_html = "".join(
        format_post_block(d["article"], d["post"], i + 1)
        for i, d in enumerate(posts_data)
    )

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;color:#1a1a1a;">
      <div style="background:#0a66c2;padding:16px 24px;border-radius:8px 8px 0 0;">
        <p style="color:#fff;margin:0;font-size:13px;font-weight:600;">
          📰 SEO Morning Post — {today}
        </p>
      </div>
      <div style="border:1px solid #e0e0e0;border-top:none;
         border-radius:0 0 8px 8px;padding:24px;">
        {blocks_html}
        <p style="font-size:11px;color:#bbb;margin:20px 0 0;text-align:center;">
          Generato da SEO Morning Post Agent · Eskimoz
        </p>
      </div>
    </div>
    """

    plain = "\n\n---\n\n".join(
        f"POST #{i+1} — {d['article']['title']}\n{d['article']['url']}\n\n{d['post']}"
        for i, d in enumerate(posts_data)
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📰 Post LinkedIn SEO ({len(posts_data)}) — {today}"
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

    log.info("Email inviata con successo.")


def main():
    log.info("=== SEO Morning Post Agent avviato ===")
    try:
        headlines  = fetch_headlines(SOURCE_URL)
        if not headlines:
            raise ValueError("Nessun titolo recuperato da SearchHerald.")

        candidates = select_articles(headlines)
        articles   = pick_readable_articles(candidates, needed=2)

        posts_data = []
        for art in articles:
            post = generate_post(art)
            posts_data.append({"article": art, "post": post})

        send_email(posts_data)
        log.info("=== Completato — %d post inviati ===", len(posts_data))
    except Exception as e:
        log.error("Errore fatale: %s", e, exc_info=True)
        raise


if __name__ == "__main__":
    main()
