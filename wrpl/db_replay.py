"""
replay_db.py — Accès SQLite pour stocker les sessions SQB.

Tables :
  sessions  — une ligne par replay SQB
  teams     — clans des deux équipes par session
  players   — stats+véhicules de chaque joueur
  lineups   — lineups dédupliquées par clan+session_slot

Les données sont supprimées 10 min après la fin d'une session.
"""

"""
TODO: Refaire les tables players pour inétgrer à l'avenir les kills avions | chars | totaux 
      Intégration du parsing des points escadron depuis le site web WT, avec comparaison des points entre chaque replays lors la visite sur le site
"""

import hashlib
import json
import logging
import shutil
import re
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger("replay_db")

ENV_DB_PATH = os.getenv("DATABASE_REPLAY", "data/sqb_data.db")
ENV_REPLAYS_PATH = os.getenv("DATABASE_REPLAYS_WRPL", "data/replays")
#PROJECT_ROOT = Path(__file__).resolve().parents[1]

#_db_path = os.getenv("DATABASE_REPLAY")
DB_PATH = os.path.abspath(ENV_DB_PATH)
REPLAYS_PATH = os.path.abspath(ENV_REPLAYS_PATH)

# ── Chargement all_units.json (singleton) ────────────────────────────────
_units_cache: dict = {}

def _load_units() -> dict:
    """
    Charge all_units.json depuis plusieurs emplacements possibles.
    Retourne le dict brut {vehicle_id: entry_dict}.
    """
    global _units_cache
    if _units_cache:
        return _units_cache
    candidates = [
        Path(__file__).parent / "all_units.json",        # wrpl/all_units.json
        Path(__file__).parent.parent / "all_units.json", # racine bot
        Path("all_units.json"),                          # cwd
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    _units_cache = json.load(f)
                log.debug("all_units.json chargé depuis %s (%d véhicules)", p, len(_units_cache))
                return _units_cache
            except Exception as exc:
                log.warning("Impossible de charger %s : %s", p, exc)
    log.warning("all_units.json introuvable — vehicle_name/type ne seront pas enrichis")
    return {}


def _enrich_vehicle(vehicle_id: str) -> tuple:
    """Retourne (vehicle_name, vehicle_type, br, image_path) depuis all_units.json."""
    if not vehicle_id:
        return "", "", 0.0
    entry = _load_units().get(vehicle_id)
    if not entry:
        return "", "", 0.0
    return (
        entry.get("full_name", ""),
        entry.get("vehicle_type", ""),
        float(entry.get("realistic_ground_br") or 0),
        entry.get("image_path", ""),
    )

# ── Normalisation du clan tag ──────────────────────────────────────────────
def normalize_clan_tag(tag: str) -> str:
    """
    Normalise un clan tag :
    - Supprime les préfixes parasites : OOPBOT{N}, COOPBOT{N}
    - Supprime les suffixes parasites : A_
    - Conserve ASCII lettres/chiffres uniquement
    - Met en majuscule

    Exemples :
      COOPBOT363XELYXA_       -> XELYX
      OOPBOT444ATAKD          -> ATAKD
      A_YUNGBOYCOOPBOT455VCOM -> VCOM
    """
    if not tag:
        return ""

    s = tag.strip()

    # Supprime suffixe A_
    s = re.sub(r"A_$", "", s, flags=re.IGNORECASE)

    # Supprime préfixe parasite : tout jusqu'à CO*PBOT + chiffres inclus
    s = re.sub(r"^.*?CO+PBOT\d+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^.*?O+PBOT\d+",  "", s, flags=re.IGNORECASE)

    # Filtre ASCII + caractères autorisés
    s = re.sub(r"[^\x00-\x7F]", "", s)
    s = re.sub(r"[^A-Za-z0-9_\-]", "", s)
    s = s.strip().upper()

    # Fallback sur tag brut si résultat trop court
    if len(s) < 2:
        fb = re.sub(r"[^\x00-\x7F]", "", tag)
        fb = re.sub(r"[^A-Za-z0-9_\-]", "", fb).upper()
        return fb if len(fb) >= 2 else s

    return s


# ── Hash de lineup pour déduplication ────────────────────────────────────
def lineup_hash(players: list[dict]) -> str:
    """Hash SHA256 d'une lineup pour détecter les doublons."""
    key = "|".join(
        f"{p['name']}:{p['vehicle']}"
        for p in sorted(players, key=lambda x: x["name"])
    )
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class ReplayDB:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                session_hex             TEXT UNIQUE NOT NULL,
                timestamp               TEXT,
                map                     TEXT,
                battle_type             TEXT,
                mode                    TEXT DEFAULT 'realistic',
                winner_team             INTEGER DEFAULT 0,
                session_slot            TEXT,   -- 'morning' | 'evening' | NULL
                inserted_at             TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teams (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id              INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                team_num                INTEGER NOT NULL,   -- 1 ou 2
                clan_tag                TEXT NOT NULL        -- normalisé majuscules
            );

            CREATE TABLE IF NOT EXISTS players (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id              INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                slot                    INTEGER,
                name                    TEXT NOT NULL,
                clan_tag                TEXT,
                vehicle                 TEXT,
                vehicle_name            TEXT,
                vehicle_type            TEXT,
                vehicle_image_patch     TEXT,
                team                    INTEGER,
                kills                   INTEGER DEFAULT 0,
                deaths                  INTEGER DEFAULT 0,
                assists                 INTEGER DEFAULT 0,
                score                   INTEGER DEFAULT 0,
                activity                REAL DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS lineup_player (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id              INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                slot                    INTEGER,
                name                    TEXT NOT NULL,
                clan_tag                TEXT,
                vehicle                 TEXT,
                vehicle_name            TEXT,
                vehicle_type            TEXT,
                vehicle_image_patch     TEXT,
                inserted_at             TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS lineups (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id              INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                clan_tag                TEXT NOT NULL,
                session_slot            TEXT,
                lineup_hash             TEXT NOT NULL,
                inserted_at             TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_hex
                ON sessions(session_hex);
            CREATE INDEX IF NOT EXISTS idx_teams_clan
                ON teams(clan_tag);
            CREATE INDEX IF NOT EXISTS idx_players_session
                ON players(session_id);
            CREATE INDEX IF NOT EXISTS idx_lineup_player_session
                ON lineup_player(session_id);
            CREATE INDEX IF NOT EXISTS idx_lineups_clan_slot
                ON lineups(clan_tag, session_slot);
            """)
        log.debug("DB initialisée : %s", self.db_path)

    # ── Lecture ─────────────────────────────────────────────────────────
    def session_exists(self, session_hex: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_hex=?", (session_hex,)
            ).fetchone()
            return row is not None

    def get_lineups_for_clan(
        self, clan_tag: str, session_slot: Optional[str] = None
    ) -> list[dict]:
        """
        Retourne les lineups d'un clan, optionnellement filtrées par session slot.
        Chaque lineup = liste de joueurs avec leur véhicule.
        """
        clan_tag = normalize_clan_tag(clan_tag)
        with self._conn() as conn:
            if session_slot:
                rows = conn.execute(
                    """SELECT l.id, l.session_id, l.lineup_hash, l.session_slot,
                              s.map, s.timestamp, s.winner_team
                       FROM lineups l JOIN sessions s ON l.session_id=s.id
                       WHERE l.clan_tag=? AND l.session_slot=?
                       ORDER BY s.inserted_at DESC""",
                    (clan_tag, session_slot),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT l.id, l.session_id, l.lineup_hash, l.session_slot,
                              s.map, s.timestamp, s.winner_team
                       FROM lineups l JOIN sessions s ON l.session_id=s.id
                       WHERE l.clan_tag=?
                       ORDER BY s.inserted_at DESC""",
                    (clan_tag,),
                ).fetchall()

            result = []
            for row in rows:
                players = conn.execute(
                    """SELECT name, clan_tag, vehicle, vehicle_name,
                              vehicle_type, team, kills, deaths, score
                       FROM players
                       WHERE session_id=? AND clan_tag=?
                       ORDER BY score DESC""",
                    (row["session_id"], clan_tag),
                ).fetchall()
                result.append({
                    "session_id":   row["session_id"],
                    "lineup_hash":  row["lineup_hash"],
                    "session_slot": row["session_slot"],
                    "map":          row["map"],
                    "timestamp":    row["timestamp"],
                    "winner_team":  row["winner_team"],
                    "players":      [dict(p) for p in players],
                })
            return result

    def get_all_sessions_for_clan(self, clan_tag: str) -> list[dict]:
        """Retourne toutes les sessions où ce clan a participé."""
        clan_tag = normalize_clan_tag(clan_tag)
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT DISTINCT s.*
                   FROM sessions s
                   JOIN teams t ON t.session_id=s.id
                   WHERE t.clan_tag=?
                   ORDER BY s.inserted_at DESC""",
                (clan_tag,),
            ).fetchall()
            result = []
            for row in rows:
                players = conn.execute(
                    "SELECT * FROM players WHERE session_id=? ORDER BY team, score DESC",
                    (row["id"],),
                ).fetchall()
                teams = conn.execute(
                    "SELECT * FROM teams WHERE session_id=?",
                    (row["id"],),
                ).fetchall()
                result.append({
                    **dict(row),
                    "players": [dict(p) for p in players],
                    "teams":   [dict(t) for t in teams],
                })
            return result

    # ── Écriture ─────────────────────────────────────────────────────────
    def insert_session(
        self,
        session_hex:  str,
        replay_data,          # ReplayData de wrpl_parser
        timestamp_str: str,
        session_slot:  Optional[str],
    ) -> int:
        """
        Insère une session SQB complète.
        Retourne l'id inséré en base.
        """
        now = datetime.now(timezone.utc).isoformat()
        hdr = replay_data.header

        with self._conn() as conn:
            # 1. Session
            cur = conn.execute(
                """INSERT OR IGNORE INTO sessions
                   (session_hex, timestamp, map, battle_type, mode,
                    winner_team, session_slot, inserted_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    session_hex,
                    timestamp_str,
                    hdr.level,
                    hdr.battle_type,
                    "realistic",
                    0,  # winner_team déterminé plus tard via is_winner
                    session_slot,
                    now,
                ),
            )
            session_db_id = cur.lastrowid
            if not session_db_id:
                # Déjà inséré
                row = conn.execute(
                    "SELECT id FROM sessions WHERE session_hex=?",
                    (session_hex,)
                ).fetchone()
                return row["id"]

            # 2. Players + clans
            clan_teams: dict[str, int] = {}  # clan_tag → team_num
            players_by_slot = {}

            for slot, p in replay_data.players.items():
                if not p.name or p.name.startswith("slot#"):
                    continue

                clan = normalize_clan_tag(p.clan_tag or "")
                if clan and p.team:
                    clan_teams[clan] = p.team

                conn.execute(
                    """INSERT INTO players
                       (session_id, slot, name, clan_tag, vehicle,
                        vehicle_name, vehicle_type, vehicle_image_patch, 
                        team, kills, deaths, assists, score, activity)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        session_db_id,
                        p.slot,
                        p.name,
                        clan,
                        p.vehicle or "",
                        (getattr(p, "vehicle_name", "") or "") or _enrich_vehicle(p.vehicle or "")[0],
                        (getattr(p, "vehicle_type", "") or "") or _enrich_vehicle(p.vehicle or "")[1],
                        (getattr(p, "vehicle_image_path", "") or "") or _enrich_vehicle(p.vehicle or "")[3],
                        p.team,
                        p.kills,
                        p.deaths,
                        p.assists,
                        p.score,
                        p.activity
                    ),
                )


                for v in p.lineup_vehicles:
                    conn.execute(
                        """INSERT INTO lineup_player
                           (session_id, slot, name, clan_tag, vehicle,
                            vehicle_name, vehicle_type, vehicle_image_patch, 
                            inserted_at)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (
                            session_db_id,
                            p.slot,
                            p.name,
                            clan,
                            v.id or "",
                            (getattr(v, "display_name", "") or "") or _enrich_vehicle(v.id or "")[0],
                            (getattr(v, "vehicle_type", "") or "") or _enrich_vehicle(v.id or "")[1],
                            (getattr(v, "image_path", "") or "") or _enrich_vehicle(v.id or "")[3],
                            now,
                        ),
                )

                if p.is_winner and p.team:
                    conn.execute(
                        "UPDATE sessions SET winner_team=? WHERE id=?",
                        (p.team, session_db_id),
                    )

                players_by_slot[slot] = p

            # 3. Teams
            for clan, team_num in clan_teams.items():
                conn.execute(
                    "INSERT INTO teams (session_id, team_num, clan_tag) VALUES (?,?,?)",
                    (session_db_id, team_num, clan),
                )

            # 4. Lineup per player (une par clan, dédupliquée)


            # 5. Lineups (une par clan, dédupliquée)
            for clan, team_num in clan_teams.items():
                team_players = [
                    {
                        "name":         p.name,
                        "vehicle":      p.vehicle or "",
                        "vehicle_name": getattr(p, "vehicle_name", "") or "",
                        "vehicle_type": getattr(p, "vehicle_type", "") or "",
                    }
                    for p in players_by_slot.values()
                    if normalize_clan_tag(p.clan_tag or "") == clan
                ]
                if not team_players:
                    continue

                lhash = lineup_hash(team_players)

                # Vérifie si cette lineup est déjà stockée pour ce clan+slot
                existing = conn.execute(
                    """SELECT 1 FROM lineups
                       WHERE clan_tag=? AND session_slot=? AND lineup_hash=?""",
                    (clan, session_slot, lhash),
                ).fetchone()

                conn.execute(
                    """INSERT INTO lineups
                       (session_id, clan_tag, session_slot, lineup_hash, inserted_at)
                       VALUES (?,?,?,?,?)""",
                    (session_db_id, clan, session_slot, lhash, now),
                )

            conn.commit()
            log.info("Session %s insérée (id=%d)", session_hex, session_db_id)
            return session_db_id

    # ── Nettoyage post-session ────────────────────────────────────────────
    def cleanup_old_sessions(self, keep_hours: int = 24):
        """
        Supprime les sessions insérées il y a plus de keep_hours.
        Appelé 10 min après la fin d'un créneau SQB.
        """
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=keep_hours)).isoformat()

        # On récupère à la fois l'ID (pour SQL) et le hex (pour le dossier) en une seule requête
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, session_hex FROM sessions WHERE inserted_at < ?", (cutoff,)
            ).fetchall()

            if not rows:
                return

            # 1. Suppression des dossiers physiques
            for row in rows:
                session_hex = row["session_hex"]
                folder_to_delete = Path(REPLAYS_PATH) / session_hex

                try:
                    if folder_to_delete.exists() and folder_to_delete.is_dir():
                        shutil.rmtree(folder_to_delete)
                        log.info("Dossier supprimé : %s", folder_to_delete.name)
                    else:
                        log.warning("Dossier introuvable pour la session %s, skipping disk cleanup.", session_hex)
                except Exception as e:
                    log.error("Erreur lors de la suppression du dossier %s : %s", session_hex, e)

            # 2. Suppression des données SQL
            for row in rows:
                sid = row["id"]
                # Note : Si vous avez configuré ON DELETE CASCADE, ces lignes sont inutiles !
                conn.execute("DELETE FROM players WHERE session_id=?", (sid,))
                conn.execute("DELETE FROM teams WHERE session_id=?", (sid,))
                conn.execute("DELETE FROM lineups WHERE session_id=?", (sid,))
                conn.execute("DELETE FROM lineup_player WHERE session_id=?", (sid,))
                conn.execute("DELETE FROM sessions WHERE id=?", (sid,))

            conn.commit()
            log.info("Nettoyage DB : %d sessions supprimées", len(rows))
