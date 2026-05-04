"""
poller.py — Polling SQB War Thunder via Playwright + httpx.

Logique :
  1. Playwright charge user_data/ (session persistante)
  2. page.evaluate() → POST /en/api/replay → JSON {"items": [...]}
  3. Pour chaque item clanBattle==True et non déjà traité :
     - item["url"] → télécharge 0000.wrpl, 0001.wrpl... via httpx async
     - parse + enrich + store dans SQLite (silencieux)

Setup initial (une seule fois) :
  python wrpl/setup_session.py
"""

import asyncio
import logging
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

import wrpl.wrpl_parser as wp

import httpx
from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger("poller")

ENV_DB_UNITS_PATH = os.getenv("DATABASE_UNITS", "data/all_units.json")
ENV_DB_REPLAYS_PATH = os.getenv("DATABASE_REPLAYS_WRPL", "data/replays")
ENV_USER_DATA_PATCH = os.getenv("USER_DATA", "user_data")


DB_UNITS    = os.path.abspath(ENV_DB_UNITS_PATH)
REPLAYS_DIR   = os.path.abspath(ENV_DB_REPLAYS_PATH)
USER_DATA_DIR = os.path.abspath(ENV_USER_DATA_PATCH)

# ── Config ────────────────────────────────────────────────────────────────
MAX_PARTS          = 30          # 0000.wrpl → 0030.wrpl max
MAX_DL_CONCURRENT  = 5           # téléchargements parallèles par session (parts d'un même item)
MAX_ITEM_CONCURRENT = 4          # items traités en parallèle dans poll_once

SQB_PAYLOAD = {
    "gameMode":         ["arcade", "realistic", "simulation"],
    "gameType":         "clanBattle",
    "techType":         "all",
    "findMissionValue": "",
    "findUserValue":    "",
    "findUserType":     "USERNAME",
    "isUserOwnReplays": False,
    "rankRange":        "",
    "timeRangeFrom":    "",
    "timeRangeTo":      "",
    "limit":            100,
    "page":             1,
} #"limit":            50,

# ── Créneaux SQB UTC ──────────────────────────────────────────────────────
def get_session_slot(dt: datetime) -> str | None:
    h = dt.hour
    if 0 <= h < 9:   return "morning"
    #if 14 <= h < 23: return "evening"
    if 14 <= h < 23: return "evening"
    return None

def get_session_window_start(dt: datetime) -> float | None:
    """
    Retourne le timestamp UTC du début du créneau SQB actuel.
    Matin  : 00h00 UTC  |  Soir : 14h00 UTC
    Permet de filtrer les replays : on ne traite que ceux
    dont startTime >= début du créneau actuel.
    """
    """h = dt.hour
    if 0 <= h < 9: #0 <= h < 9
        return dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    if 14 <= h < 23: #14 <= h < 23
        return dt.replace(hour=14, minute=0, second=0, microsecond=0).timestamp()
    return None"""

    h = dt.hour
    if 0 <= h < 9:  # 0 <= h < 9
        return dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    if 14 <= h < 23:  # 14 <= h < 23
        return dt.replace(hour=14, minute=0, second=0, microsecond=0).timestamp()
    return None

def is_sqb_window() -> bool:
    return get_session_slot(datetime.now(timezone.utc)) is not None
    #return True


# ── Téléchargement async des .wrpl ────────────────────────────────────────
WRPL_MAGIC    = bytes([0xe5, 0xac, 0x00, 0x10])
WRPL_MIN_SIZE = 1226  # taille header minimum

async def _download_part(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
) -> bool:
    """
    Télécharge un fichier .wrpl et valide le magic byte e5ac0010.
    Retourne True uniquement si c'est un vrai replay WT.
    Gère les 429 avec backoff sur Retry-After.
    """
    for attempt in range(3):
        try:
            r = await client.get(url, follow_redirects=True, timeout=30)

            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 10 * (attempt + 1)))
                log.warning("429 Too Many Requests %s — attente %ds", url, retry_after)
                await asyncio.sleep(retry_after)
                continue

            if r.status_code != 200:
                return False

            content = r.content
            if len(content) < WRPL_MIN_SIZE or content[:4] != WRPL_MAGIC:
                log.debug("Fichier invalide reçu pour %s (%d octets, magic=%s)",
                          url, len(content), content[:4].hex() if content else "vide")
                return False
            dest.write_bytes(content)
            return True

        except Exception as exc:
            log.debug("Erreur téléchargement %s (tentative %d) : %s", url, attempt + 1, exc)
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)

    return False


async def download_wrpl_files(
    base_url: str,
    session_hex: str,
    dest_dir: Path,
    user_agent: str,
    cookies: dict,
) -> list[str]:
    """
    Télécharge les fichiers .wrpl d'une session en parallèle (MAX_DL_CONCURRENT).
    Procède par batches : si un part est absent dans le batch, on arrête.
    base_url = item["url"]  ex: "https://wt-game-replays.warthunder.com/064c8aa.../"
    Retourne la liste des chemins téléchargés (ordonnés).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": user_agent,
        "Referer":    "https://warthunder.com/",
    }

    sem = asyncio.Semaphore(MAX_DL_CONCURRENT)

    async def try_part(part_idx: int) -> tuple[int, str | None]:
        part_name = f"{part_idx:04d}.wrpl"
        file_url  = f"{base_url.rstrip('/')}/{part_name}"
        file_path = dest_dir / part_name

        # Skip si déjà valide en cache
        if file_path.exists() and file_path.stat().st_size >= WRPL_MIN_SIZE:
            try:
                if file_path.read_bytes()[:4] == WRPL_MAGIC:
                    return part_idx, str(file_path)
            except Exception:
                pass
            try:
                file_path.unlink()
            except Exception:
                pass

        async with sem:
            ok = await _download_part(client, file_url, file_path)

        if ok:
            log.debug("  %s/%s OK", session_hex, part_name)
            return part_idx, str(file_path)
        else:
            log.debug("  %s : absent à %s", session_hex, part_name)
            return part_idx, None

    downloaded: list[str] = []

    async with httpx.AsyncClient(headers=headers, cookies=cookies) as client:
        for batch_start in range(0, MAX_PARTS, MAX_DL_CONCURRENT):
            batch = range(batch_start, min(batch_start + MAX_DL_CONCURRENT, MAX_PARTS))
            results = await asyncio.gather(*[try_part(i) for i in batch])
            results.sort(key=lambda x: x[0])

            gap_found = False
            for _idx, path in results:
                if path is None:
                    gap_found = True
                    break
                downloaded.append(path)

            if gap_found:
                break

    return downloaded


# ── Classe principale ─────────────────────────────────────────────────────
class WTPoller:
    """
    Gère le polling SQB War Thunder.
    Une seule instance par bot — lancée dans on_ready, fermée à l'arrêt.
    """

    def __init__(self, db):
        self.db          = db
        self._playwright = None
        self._context    = None
        self._page       = None
        self._running    = False
        # Mis à jour après chaque goto()
        self._user_agent  = ""
        self._cookies     = {}

    # ── Cycle de vie ─────────────────────────────────────────────────────
    async def start(self):
        """Lance Playwright headless + charge la session WT depuis user_data/."""
        from playwright.async_api import async_playwright

        log.info("Démarrage Playwright...")
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",  # nécessaire sous Linux/Docker
                "--disable-dev-shm-usage"  # évite les crashs mémoire
            ],
        )
        self._page = (self._context.pages[0] if self._context.pages
                      else await self._context.new_page())

        # Charge la page une fois pour activer les cookies
        await self._page.goto(
            "https://warthunder.com/en/tournament/replay/",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        # Extrait user_agent et cookies (comme dans acess_wt_api.py)
        self._user_agent = await self._page.evaluate("navigator.userAgent")
        raw_cookies      = await self._context.cookies()
        self._cookies    = {c["name"]: c["value"] for c in raw_cookies}

        log.info("Playwright prêt — %d cookies chargés", len(self._cookies))

    async def stop(self):
        """Ferme Playwright proprement."""
        self._running = False
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
        log.info("Playwright arrêté")

    # ── Requête API ───────────────────────────────────────────────────────
    async def _fetch_sqb_items(self, page_num: int = 1) -> list[dict]:
        payload = {**SQB_PAYLOAD, "page": page_num}
        try:
            current_url = self._page.url
            log.info("URL actuelle : %s", current_url)

            if "warthunder.com" not in current_url:
                await self._page.goto(
                    "https://warthunder.com/en/tournament/replay/",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                log.info("Navigué vers warthunder.com")

            # Test : vérifier que la page est bien chargée et connectée
            title = await self._page.title()
            log.info("Titre de la page : %s", title)

            # Test : vérifier le statut HTTP de l'API directement
            result = await self._page.evaluate(
                """async (payload) => {
                    try {
                        const r = await fetch("https://warthunder.com/en/api/replay", {
                            method:  "POST",
                            headers: { "Content-Type": "application/json" },
                            body:    JSON.stringify(payload)
                        });
                        return { status: r.status, ok: r.ok, body: await r.text() };
                    } catch (e) {
                        return { error: e.toString() };
                    }
                }""",
                payload,
            )

            log.info("Résultat brut API : %s", str(result)[:500])

            if "error" in result:
                log.error("Fetch JS error : %s", result["error"])
                return []
            if not result.get("ok"):
                log.error("HTTP %s — body : %s", result.get("status"), result.get("body", "")[:200])
                return []

            import json
            data = json.loads(result["body"])
            items = data.get("items") or []
            log.info("API page %d → %d items", page_num, len(items))
            return items

        except Exception as exc:
            log.error("_fetch_sqb_items exception : %s", exc)
            return []

    # ── Traitement d'un item ──────────────────────────────────────────────
    async def _process_item(self, item: dict) -> bool:
        """
        Télécharge et parse un item SQB.
        Retourne True si inséré en base avec succès.
        """
        # Filtre SQB
        if not (item.get("clanBattle") or item.get("gameType") == "clanBattle"):
            return False

        # URL de base pour les .wrpl
        base_url = item.get("url", "")
        if not base_url:
            return False

        # session_hex depuis sessionIdHex ou converti depuis sessionId
        session_hex = item.get("sessionIdHex") or item.get("id")
        if not session_hex:
            try:
                session_hex = hex(int(item["sessionId"]))[2:]
            except (KeyError, ValueError, TypeError):
                log.warning("Impossible d'extraire session_hex : %s", item)
                return False

        # Déjà en base ?
        if self.db.session_exists(session_hex):
            return False

        # Filtrer les replays hors du créneau actuel
        # → évite de remonter dans la session précédente au démarrage
        now_utc  = datetime.now(timezone.utc)
        now_ts   = now_utc.timestamp()
        window_start = get_session_window_start(now_utc)
        start_time   = item.get("startTime", 0)
        if window_start and start_time and start_time < window_start:
            log.debug("SQB %s hors créneau (startTime=%s < window=%s) — ignoré",
                      session_hex, start_time, window_start)
            return False

        """# Attendre 10 min après la fin avant téléchargement
        end_time = item.get("endTime", 0)
        if end_time and (now_ts - end_time) < 600:
            log.debug("SQB %s terminé depuis moins de 10 min — attente", session_hex)
            return False"""

        log.info("Nouveau SQB : %s — %s", session_hex, item.get("title", ""))

        # Téléchargement via httpx async (ne bloque pas asyncio)
        dest = Path(f"{REPLAYS_DIR}/{session_hex}")

        wrpl_files = None
        last_error = None

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            log.info("Tentative %d/%d de téléchargement...", attempt, max_retries)

            try:
                wrpl_files = await download_wrpl_files(
                    base_url, session_hex, dest,
                    self._user_agent, self._cookies,
                )

                if wrpl_files:
                    log.info("✓ Téléchargement réussi : %d fichiers", len(wrpl_files))
                    break

            except Exception as exc:
                log.error("Erreur tentative %d: %s", attempt, exc)
                last_error = exc
                wrpl_files = None

            if attempt < max_retries and not wrpl_files:
                wait_time = 5 * attempt
                log.warning("Échec tentative %d. Attente %d sec avant retry...",
                            attempt, wait_time)
                await asyncio.sleep(wait_time)

        if not wrpl_files:
            log.warning("Impossible de télécharger après %d tentatives %s",
                        max_retries,
                        f"(dernier erreur: {last_error})" if last_error else "")
            return False

        total_size = sum(Path(f).stat().st_size for f in wrpl_files)
        log.info("  %d fichiers téléchargés pour %s (total: %s ko)",
                 len(wrpl_files), session_hex, total_size // 1024)

        # Parse (dans un thread pour ne pas bloquer asyncio)
        #sys.path.insert(0, str(Path(__file__).parent))

        log.info("  Type des replays %s", type(wrpl_files))

        for file in wrpl_files:
            log.info("  Replay %s", file)
            log.info("  Type du nom du replay %s", type(file))
        try:
            replay_data = await asyncio.to_thread(
                wp.parse_replay_files, wrpl_files, False
            )
        except Exception as exc:
            log.error("parse_replay_files %s : %s", session_hex, exc)
            log.exception("Erreur critique lors du parsing pour la session %s", session_hex)
            traceback.print_exc()
            return False

        # Stockage SQLite
        slot = get_session_slot(datetime.now(timezone.utc))
        ts   = datetime.fromtimestamp(
            item.get("startTime", 0), tz=timezone.utc
        ).isoformat()

        self.db.insert_session(
            session_hex=session_hex,
            replay_data=replay_data,
            timestamp_str=ts,
            session_slot=slot,
        )
        log.info("SQB %s stocké (slot=%s)", session_hex, slot)
        return True

    # ── Boucle de polling ─────────────────────────────────────────────────
    async def poll_once(self):
        """
        Un cycle : parcourt les pages de l'API, collecte les items inconnus,
        puis les traite en parallèle (MAX_ITEM_CONCURRENT à la fois).
        """
        page = 1
        new_count_total = 0
        known_streak = 0
        pending_items: list[dict] = []
        stop_pagination = False

        # ── Phase 1 : collecte des items inconnus (rapide, séquentielle) ──
        while not stop_pagination:
            items = await self._fetch_sqb_items(page_num=page)
            if not items:
                break

            for item in items:
                sid = item.get("sessionIdHex") or ""
                if not sid:
                    try:
                        sid = hex(int(item.get("sessionId", 0)))[2:]
                    except Exception:
                        continue

                window_start = get_session_window_start(datetime.now(timezone.utc))
                item_start = item.get("startTime", 0)
                if window_start and item_start and item_start < window_start:
                    log.debug("SQB %s hors créneau → arrêt pagination", sid)
                    stop_pagination = True
                    break

                if self.db.session_exists(sid):
                    known_streak += 1
                    log.debug("SQB %s déjà connu (%d consécutifs)", sid, known_streak)
                    continue

                known_streak = 0
                pending_items.append(item)

            if stop_pagination:
                break

            page += 1

        if not pending_items:
            return

        log.info("poll_once : %d item(s) inconnu(s) à traiter en parallèle", len(pending_items))

        # ── Phase 2 : traitement concurrent avec semaphore ──────────────────
        sem = asyncio.Semaphore(MAX_ITEM_CONCURRENT)

        async def process_with_sem(item: dict) -> bool:
            async with sem:
                sid = item.get("sessionIdHex") or item.get("id", "?")
                try:
                    return await self._process_item(item)
                except (asyncio.CancelledError, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    log.exception("_process_item %s : %s", sid, exc)
                    return False

        results = await asyncio.gather(*[process_with_sem(it) for it in pending_items])
        new_count_total = sum(1 for r in results if r)

        if new_count_total > 0:
            log.info("Cycle terminé : %d nouveau(x) SQB traité(s)", new_count_total)

    async def poll_loop(self, interval_seconds: int = 120):
        """
        Boucle principale asyncio — lancée depuis main.py via bot.loop.create_task().
        Polling actif uniquement dans les créneaux SQB (00h-09h et 14h-23h UTC).
        """
        self._running = True
        log.info("Poll loop démarrée (intervalle=%ds)", interval_seconds)

        while self._running:
            if is_sqb_window():
                try:
                    await self.poll_once()
                except (asyncio.CancelledError, KeyboardInterrupt):
                    log.info("Poll loop annulée proprement")
                    return
                except Exception as exc:
                    log.error("poll_once erreur : %s", exc)

            else:
                log.debug("Hors créneau SQB — polling suspendu")

            try:
                await asyncio.sleep(interval_seconds)
            except (asyncio.CancelledError, KeyboardInterrupt):
                log.info("Poll loop interrompue proprement")
                return
