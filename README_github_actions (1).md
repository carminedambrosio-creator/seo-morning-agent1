# SEO Morning Post Agent — Setup GitHub Actions

Tempo stimato: 10 minuti. Non serve nessun server.

---

## Passo 1 — Crea il repository su GitHub

1. Vai su https://github.com/new
2. Nome: `seo-morning-agent` (o come preferisci)
3. Seleziona **Private** (importante, contiene le tue credenziali)
4. Clicca **Create repository**

---

## Passo 2 — Carica i file

Nella pagina del repository appena creato:

1. Clicca **uploading an existing file** (o "Add file → Upload files")
2. Carica questi tre file:
   - `agent.py`
   - `requirements.txt`
3. Poi crea manualmente la cartella `.github/workflows/`:
   - Clicca **Add file → Create new file**
   - Nel campo nome scrivi: `.github/workflows/morning_post.yml`
   - Incolla il contenuto del file `morning_post.yml`
   - Clicca **Commit new file**

---

## Passo 3 — Aggiungi i Secrets (credenziali)

I secrets sono variabili cifrate, non visibili a nessuno (nemmeno a te dopo averle salvate).

1. Nel repository, vai su **Settings → Secrets and variables → Actions**
2. Clicca **New repository secret** per ognuno di questi:

| Nome secret | Valore |
|---|---|
| `ANTHROPIC_API_KEY` | La tua chiave API Anthropic (da console.anthropic.com) |
| `EMAIL_FROM` | L'email mittente (es. `tuonome@gmail.com`) |
| `EMAIL_TO` | La tua email dove ricevere il post (es. `carmine@eskimoz.it`) |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Stessa email di `EMAIL_FROM` |
| `SMTP_PASS` | La tua App Password Gmail (vedi Passo 4) |

---

## Passo 4 — App Password Gmail

Gmail non accetta la password normale via SMTP. Serve una "App Password":

1. Vai su https://myaccount.google.com/security
2. Assicurati che la **Verifica in due passaggi** sia attiva
3. Cerca **Password per le app** (o vai su https://myaccount.google.com/apppasswords)
4. Dai un nome tipo "SEO Agent" e clicca **Crea**
5. Copia la password di 16 caratteri generata
6. Usala come valore del secret `SMTP_PASS`

---

## Passo 5 — Verifica che funzioni (test manuale)

Prima di aspettare le 08:00, fai un test subito:

1. Nel repository vai su **Actions**
2. Clicca il workflow **SEO Morning Post Agent**
3. Clicca **Run workflow → Run workflow**
4. Aspetta ~1 minuto e controlla la tua email

Se vedi la spunta verde ✅ tutto funziona.
Se vedi ❌ clicca sul run per leggere il log di errore.

---

## Orario

Il cron è impostato su `0 6 * * 1-5` (lunedì-venerdì):
- **06:00 UTC = 08:00 ora solare italiana** (ottobre–marzo)
- **06:00 UTC = 07:00 ora legale italiana** (marzo–ottobre)

Per avere le 08:00 esatte tutto l'anno, cambia il cron in `morning_post.yml`:
- Ora solare (ott–mar): `0 6 * * 1-5`
- Ora legale (mar–ott): `0 7 * * 1-5`

Oppure lascia `0 6 * * 1-5` e ricevi l'email alle 07:00 in estate — di solito non è un problema.

---

## Note utili

- GitHub Actions è **gratuito** per repository privati fino a 2.000 minuti/mese. Questo script gira ~1 minuto al giorno: usi circa 20 minuti al mese, ampiamente nei limiti.
- Puoi sempre lanciarlo manualmente dal pannello **Actions → Run workflow**.
- I log di ogni esecuzione restano visibili su GitHub per 90 giorni.
