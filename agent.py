#!/usr/bin/env python3
"""
SEO Morning Post Agent
Ogni mattina alle 08:00 analizza SearchHerald, seleziona 1-2 notizie
SEO/AI rilevanti e genera un post LinkedIn in stile Eskimoz via email.
"""

import os
import re
import json
import smtplib
import logging
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
import logging
import os

# Create logs directory if it doesn't exist
import os
os.makedirs("logs", exist_ok=True)

# Configure logging
logging.basicConfig(
    filename=os.path.join(log_dir, 'seo_agent.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# ---------------------------------------------------------------------------
# CONFIGURAZIONE — modifica questi valori o usali come variabili d'ambiente
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "sk-ant-XXXXXXXXXX")
EMAIL_FROM        = os.getenv("EMAIL_FROM",        "agent@tuodominio.com")
EMAIL_TO          = os.getenv("EMAIL_TO",          "carmine@eskimoz.it")
SMTP_HOST         = os.getenv("SMTP_HOST",         "smtp.gmail.com")
SMTP_PORT         = int(os.getenv("SMTP_PORT",     "587"))
SMTP_USER         = os.getenv("SMTP_USER",         "agent@tuodominio.com")
SMTP_PASS         = os.getenv("SMTP_PASS",         "la-tua-app-password")

SOURCE_URL  = "https://searchherald.com/"
LOG_FILE    = "logs/seo_agent.log"
MODEL       = "claude-sonnet-4-20250514"
MAX_TOKENS  = 1200
# ---------------------------------------------------------------------------
import os

LOG_FILE = 'logs/seo_agent.log'
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)  # ← aggiunge questa riga

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def fetch_headlines(url: str) -> list[dict]:
    """Scarica i titoli dal SearchHerald."""
    log.info("Recupero titoli da %s", url)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SEOAgent/1.0)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    headlines = []
    seen = set()
    # Il SearchHerald usa <h2> con <a> per ogni notizia
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
        # Rimuovi nav, header, footer, sidebar
        for tag in soup(["nav", "header", "footer", "aside", "script", "style"]):
            tag.decompose()
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text()) > 60]
        text = " ".join(paragraphs)
        return text[:max_chars]
    except Exception as e:
        log.warning("Impossibile leggere %s: %s", url, e)
        return ""


def call_claude(system: str, user: str) -> str:
    """Chiama l'API Anthropic e restituisce il testo della risposta."""
    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}]
    }
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
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def select_articles(headlines: list[dict]) -> list[dict]:
    """Usa Claude per selezionare i 2 articoli più rilevanti."""
    log.info("Selezione articoli con Claude...")
    system = (
        "Sei un esperto SEO e AI strategist. Analizza questi titoli di notizie SEO/AI "
        "e seleziona i 2 più rilevanti e attuali per un professionista SEO italiano nel 2026. "
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
    for item in data.get("selected", [])[:2]:
        idx = item.get("index", 0)
        selected.append({
            "title": item.get("title") or headlines[idx]["title"],
            "url":   item.get("url")   or headlines[idx]["url"],
            "why":   item.get("why", "")
        })
    log.info("Selezionati: %s", [a["title"][:60] for a in selected])
    return selected


def generate_post(articles: list[dict]) -> str:
    """Genera il post LinkedIn in stile Eskimoz."""
    log.info("Generazione post LinkedIn...")
    content_parts = []
    for art in articles:
        log.info("Leggo: %s", art["url"])
        text = fetch_article_text(art["url"])
        content_parts.append(f"=== {art['title']} ===\n{text or 'Contenuto non disponibile.'}")
    full_content = "\n\n".join(content_parts)

    system = (
        "Sei Carmine, Client & SEO Director di Eskimoz, agenzia SEO italiana. "
        "Scrivi UN post LinkedIn in italiano basato sulle notizie qui sotto.\n\n"
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
    post = call_claude(system, full_content)
    log.info("Post generato (%d caratteri)", len(post))
    return post


def send_email(post: str, articles: list[dict]) -> None:
    """Invia il post via email con layout HTML."""
    log.info("Invio email a %s...", EMAIL_TO)
    today = datetime.now().strftime("%d %B %Y")

    articles_html = "".join(
        f'<li style="margin-bottom:4px;">'
        f'<a href="{a["url"]}" style="color:#0a66c2;">{a["title"]}</a>'
        f'<span style="color:#888; font-size:12px;"> — {a["why"]}</span></li>'
        for a in articles
    )

    post_html = post.replace("\n", "<br>")
    # bold markdown → <strong>
    post_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", post_html)

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;color:#1a1a1a;">
      <div style="background:#0a66c2;padding:16px 24px;border-radius:8px 8px 0 0;">
        <p style="color:#fff;margin:0;font-size:13px;font-weight:600;">
          📰 SEO Morning Post — {today}
        </p>
      </div>
      <div style="border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px;padding:24px;">
        <p style="font-size:12px;color:#888;margin:0 0 12px;">Articoli analizzati:</p>
        <ul style="font-size:13px;padding-left:20px;margin:0 0 24px;">{articles_html}</ul>
        <hr style="border:none;border-top:1px solid #eee;margin:0 0 20px;">
        <p style="font-size:12px;color:#888;margin:0 0 12px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;">Post generato</p>
        <div style="background:#f7f9fb;border-left:3px solid #0a66c2;padding:16px 20px;border-radius:0 6px 6px 0;font-size:14px;line-height:1.75;">
          {post_html}
        </div>
        <p style="font-size:11px;color:#bbb;margin:20px 0 0;text-align:center;">
          Generato da SEO Morning Post Agent · Eskimoz
        </p>
      </div>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📰 Post LinkedIn SEO — {today}"
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(post, "plain", "utf-8"))
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
        headlines = fetch_headlines(SOURCE_URL)
        if not headlines:
            raise ValueError("Nessun titolo recuperato da SearchHerald.")
        articles = select_articles(headlines)
        post     = generate_post(articles)
        send_email(post, articles)
        log.info("=== Completato ===")
    except Exception as e:
        log.error("Errore fatale: %s", e, exc_info=True)
        raise


if __name__ == "__main__":
    main()
