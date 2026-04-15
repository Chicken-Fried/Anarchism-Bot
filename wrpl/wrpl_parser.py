"""
wrpl_parser.py — Parseur complet de replays War Thunder (.wrpl)
Reverse-engineeré depuis https://github.com/maxsupermanhd/wrpl-inspector

Sources d'information croisées :
  - Settings BLK  : liste statique des joueurs + véhicules (disponible dès le header)
  - Paquets Slot  : PlayerInit dynamique (noms, clans, UserID, par slot 0-255)
  - Paquets Kill  : kills avec vehicle du killer et slot
  - Paquets Award : récompenses par slot
  - Paquets Chat  : messages in-game
  - Paquets Move  : positions XYZ des entités (optionnel)
  - Results BLK   : statistiques de fin de partie

Dépendances :
    pip install zstandard          # pour les BLK FAT_ZSTD (replays récents)
    pip install lz4                # pour les paquets ECS compressés (optionnel)

Usage :
    python wrpl_parser.py replay.wrpl
    python wrpl_parser.py replay.wrpl --json output.json
    python wrpl_parser.py replay.wrpl --csv
    python wrpl_parser.py replay.wrpl --movements --json full.json
    python wrpl_parser.py --download <session_hex>  # télécharge depuis les serveurs Gaijin
"""

import struct
import zlib
import io
import json
import argparse
import difflib
import math
import sys
import re
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Tuple
from pathlib import Path
from playwright.sync_api import sync_playwright


# =============================================================================
# 1. HEADER BINAIRE (1226 octets fixes)
# =============================================================================

MAGIC = bytes([0xe5, 0xac, 0x00, 0x10])

# Correspond exactement à WRPLHeader dans header.go
# Les champs Raw_Unknown* sont conservés pour extraire is_server
HEADER_FORMAT = "<4si128s260s128s128s32siB35sI4sQB3sIH30s128sIII48s128s128s2s"
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)  # 1226 octets


def _fetch_page(url: str, verbose: bool = False) -> str:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Attendre que Cloudflare laisse passer
            page.wait_for_selector("table", timeout=6000)

            html = page.content()
            browser.close()
            return html
    except Exception as e:
        if verbose:
            print(f"  [online] Impossible de récupérer {url} : {e}")
        return ""

def _get_json(url: str, timeout: int = 30) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "wrpl-parser/1.0",
                                                "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


@dataclass
class WRPLHeader:
    magic:              bytes
    version:            int
    level:              str
    level_settings:     str
    battle_type:        str
    environment:        str
    visibility:         str
    results_blk_offset: int
    difficulty:         int
    session_type:       int
    session_id:         int
    replay_part_number: int
    mset_size:          int
    settings_blk_size:  int
    loc_name:           str
    start_time:         int
    time_limit:         int
    score_limit:        int
    battle_class:       str
    battle_kill_streak: str
    is_server:          bool = False

    @property
    def session_hex(self) -> str:
        return f"{self.session_id:016x}"


def _cstr(b: bytes) -> str:
    end = b.find(b'\x00')
    return b[:end].decode('utf-8', errors='replace') if end >= 0 else b.decode('utf-8', errors='replace')


def parse_header(data: bytes) -> WRPLHeader:
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Fichier trop court pour le header : {len(data)} < {HEADER_SIZE}")

    (magic, version, raw_level, raw_level_settings, raw_battle_type,
     raw_environment, raw_visibility, results_blk_offset, difficulty,
     raw_unk0, session_type, raw_unk1, session_id, replay_part_number,
     raw_unk2, mset_size, settings_blk_size, raw_unk3, raw_loc_name,
     start_time, time_limit, score_limit, raw_unk4, raw_battle_class,
     raw_battle_kill_streak, raw_unk5) = struct.unpack_from(HEADER_FORMAT, data, 0)

    if magic != MAGIC:
        raise ValueError(f"Magic invalide : {magic.hex()} (attendu e5ac0010)")

    # Raw_Unknown2 : octet [1] == 0x5a → replay côté serveur
    is_server = (raw_unk2[1:2] == b'\x5a')

    return WRPLHeader(
        magic=magic, version=version,
        level=_cstr(raw_level), level_settings=_cstr(raw_level_settings),
        battle_type=_cstr(raw_battle_type), environment=_cstr(raw_environment),
        visibility=_cstr(raw_visibility), results_blk_offset=results_blk_offset,
        difficulty=difficulty, session_type=session_type, session_id=session_id,
        replay_part_number=replay_part_number, mset_size=mset_size,
        settings_blk_size=settings_blk_size, loc_name=_cstr(raw_loc_name),
        start_time=start_time, time_limit=time_limit, score_limit=score_limit,
        battle_class=_cstr(raw_battle_class),
        battle_kill_streak=_cstr(raw_battle_kill_streak),
        is_server=is_server,
    )


# =============================================================================
# 2. TAILLE VARIABLE (ReadVariableLengthSize — util.go/packet)
# =============================================================================

def read_vlsize(stream) -> Optional[int]:
    """Préfixe de taille 1–5 octets. Retourne None sur EOF."""
    b = stream.read(1)
    if not b:
        return None
    first = b[0]

    if first & 0x80:
        if first & 0x40:
            raise ValueError(f"Préfixe VL invalide : 0x{first:02x}")
        return first & 0x7F                                     # 10xxxxxx
    elif first & 0x40:                                          # 01xxxxxx  2 octets
        b1 = stream.read(1)[0]
        return ((first << 8) | b1) ^ 0x4000
    elif first & 0x20:                                          # 001xxxxx  3 octets
        b12 = stream.read(2)
        return ((first << 16) | (b12[0] << 8) | b12[1]) ^ 0x200000
    elif first & 0x10:                                          # 0001xxxx  4 octets
        b123 = stream.read(3)
        return ((first << 24) | (b123[0] << 16) | (b123[1] << 8) | b123[2]) ^ 0x10000000
    else:                                                       # 0000xxxx  5 octets LE u32
        return struct.unpack_from('<I', stream.read(4))[0]


# =============================================================================
# 3. LECTURE DU FLUX DE PAQUETS (PacketStreamReader — packetReader.go)
# =============================================================================

@dataclass
class RawPacket:
    seq:          int
    current_time: int    # ms depuis le début de la partie
    packet_type:  int
    payload:      bytes

    TYPE_NAMES = {
        0: "EndMarker", 1: "StartMarker", 2: "AircraftSmall",
        3: "Chat",      4: "MPI",         5: "NextSegment",
        6: "ECS",       7: "Snapshot",    8: "ReplayHeaderInfo",
    }

    @property
    def type_name(self) -> str:
        return self.TYPE_NAMES.get(self.packet_type, f"Unknown({self.packet_type})")

    @property
    def time_s(self) -> float:
        return self.current_time / 1000.0


def read_packets(stream):
    """Générateur → RawPacket depuis le flux décompressé."""
    current_time = 0
    seq = 0

    while True:
        # Lecture taille du paquet (variable length encoding)
        packet_size = read_vlsize(stream)
        if packet_size is None:
            return
        if packet_size == 0:
            continue

        # Lecture header (2 octets minimum)
        hdr = stream.read(2)
        if len(hdr) < 2:
            return

        ptype = hdr[0] # Byte 0 contient le type + flags

        # Vérification flag "Pas de timestamp" (Bit 4)
        if ptype & 0b00010000:
            # Pas de timestamp dans ce paquet
            # On réutilise le dernier timestamp connu
            ptype ^= 0b00010000 # Masquage du flag pour obtenir type réel
            payload_size = packet_size - 2 # Seulement header(2)
        else:
            # Timestamp présent dans ce paquet
            ts = stream.read(4)
            if len(ts) < 4:
                return
            current_time = struct.unpack_from('<I', ts)[0]
            payload_size = packet_size - 6 # Header(2) + Timestamp(4)

        # Lecture du payload
        payload = stream.read(payload_size) if payload_size > 0 else b''
        if len(payload) < payload_size:
            return

        # Vérifie si le payload contient la chaîne 'il_merkava_mk_1b'

        """if b'\rt1_player' in payload:
            print(f"PAYLOAD RT1_PLAYER | TYPE {ptype}   : {payload}\n")"""

        """if b'cn_ztl_11' in payload:
            print(f"PAYLOAD CONTAINS ZLT 11: {payload}\n")"""

        """if b'germ_begleitpanzer_57' in payload:
            print(f"PAYLOAD CONTAINS BEGLEITPANZER 57: {payload}\n")"""

        yield RawPacket(seq=seq, current_time=current_time,
                        packet_type=ptype, payload=payload)
        seq += 1


# =============================================================================
# 4. HELPERS DE LECTURE BINAIRE
# =============================================================================

def read_lenstr(data: bytes, offset: int) -> Tuple[str, int]:
    """Lit une chaîne de caractères préfixée par un octet de longueur."""
    if offset >= len(data):
        raise ValueError(f"read_lenstr: offset {offset} hors limites ({len(data)})")
    length = data[offset]
    if offset + 1 + length > len(data):
        raise ValueError(f"read_lenstr: longueur {length} invalide à l'offset {offset}")
    s = data[offset + 1 : offset + 1 + length].decode('utf-8', errors='replace')
    return s, offset + 1 + length


def read_uleb128(data: bytes, offset: int) -> tuple[int, int]:
    """ULEB-128 (uleb128 — blk.go)."""
    val, shift = 0, 0
    while offset < len(data):
        b = data[offset]; offset += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, offset
        shift += 7
        if shift > 63:
            raise ValueError("uleb128 overflow")
    raise ValueError("uleb128: buffer trop court")


# =============================================================================
# 5. PARSER BLK FAT (blk.go — parseFatBlk)
# =============================================================================

def parse_fat_blk(buf: bytes) -> dict:
    p = 0

    _, p  = read_uleb128(buf, p)          # names_count (ignoré)
    ns, p = read_uleb128(buf, p)          # names_size
    names_raw = buf[p : p + ns]; p += ns
    names = [s.decode('utf-8', errors='replace') for s in names_raw.split(b'\x00')]

    total_blocks, p = read_uleb128(buf, p)
    params_count, p = read_uleb128(buf, p)
    params_data_sz, p = read_uleb128(buf, p)
    params_data = buf[p : p + params_data_sz]; p += params_data_sz
    params_info = buf[p : p + params_count * 8]; p += params_count * 8
    block_info  = buf[p:]

    # --- descripteurs de blocs ---
    bp = 0
    descs = []
    for _ in range(total_blocks):
        name_id,     bp = read_uleb128(block_info, bp)
        field_count, bp = read_uleb128(block_info, bp)
        child_count, bp = read_uleb128(block_info, bp)
        first_child  = 0
        if child_count > 0:
            first_child, bp = read_uleb128(block_info, bp)
        descs.append((int(name_id), int(field_count), int(child_count), int(first_child)))

    # --- lecture d'un paramètre ---
    def get_param(index: int):
        start = index * 8
        chunk = params_info[start : start + 8]
        name_id = chunk[0] | (chunk[1] << 8) | (chunk[2] << 16)
        type_id = chunk[3]
        data    = chunk[4:8]
        name    = names[name_id] if name_id < len(names) else f"?{name_id}"

        def rf32(b):  return struct.unpack_from('<f', b)[0]
        def ri32(b):  return struct.unpack_from('<i', b)[0]
        def ru32(b):  return struct.unpack_from('<I', b)[0]
        def at(o, n): return params_data[o : o + n]

        if   type_id == 0x01:  # STRING
            raw  = ru32(data)
            in_nm = (raw >> 31) == 1
            off   = raw & 0x7FFFFFFF
            if in_nm:
                value = names[off] if off < len(names) else ""
            else:
                end   = params_data.index(b'\x00', off)
                value = params_data[off:end].decode('utf-8', errors='replace')
        elif type_id == 0x02:  value = ri32(data)
        elif type_id == 0x03:  value = rf32(data)
        elif type_id == 0x04:
            o = ru32(data); b = at(o, 8);  value = [rf32(b[0:4]),  rf32(b[4:8])]
        elif type_id == 0x05:
            o = ru32(data); b = at(o, 12); value = [rf32(b[i*4:(i+1)*4]) for i in range(3)]
        elif type_id == 0x06:
            o = ru32(data); b = at(o, 16); value = [rf32(b[i*4:(i+1)*4]) for i in range(4)]
        elif type_id == 0x07:
            o = ru32(data); b = at(o, 8)
            value = [struct.unpack_from('<i', b, i*4)[0] for i in range(2)]
        elif type_id == 0x08:
            o = ru32(data); b = at(o, 12)
            value = [struct.unpack_from('<i', b, i*4)[0] for i in range(3)]
        elif type_id == 0x09:  value = ru32(data) != 0
        elif type_id == 0x0A:  value = list(data)           # RGBA
        elif type_id == 0x0B:                                # FLOAT12 (matrice 3×4)
            o = ru32(data); b = at(o, 48)
            value = [[rf32(b[(r*3+c)*4:(r*3+c+1)*4]) for c in range(3)] for r in range(4)]
        elif type_id == 0x0C:
            o = ru32(data)
            value = struct.unpack_from('<q', params_data, o)[0]
        elif type_id == 0x0D:
            o = ru32(data); b = at(o, 16)
            value = [struct.unpack_from('<i', b, i*4)[0] for i in range(4)]
        else:
            value = f"type:0x{type_id:02x}:{data.hex()}"
        return name, value

    # --- assemblage ---
    def put_kv(m, k, v):
        if k in m:
            existing = m[k]
            m[k] = existing + [v] if isinstance(existing, list) else [existing, v]
        else:
            m[k] = v

    param_ptr = 0
    flat = []
    for (name_id, fc, cc, fch) in descs:
        bname = "root" if name_id == 0 else (names[name_id - 1] if name_id - 1 < len(names) else f"?{name_id}")
        fields = []
        for j in range(fc):
            try:
                n, v = get_param(param_ptr + j)
                fields.append((n, v))
            except Exception:
                pass
        param_ptr += fc
        flat.append((bname, fields, cc, fch))

    def build(idx: int) -> dict:
        bname, fields, cc, fch = flat[idx]
        m = {}
        for k, v in fields:
            put_kv(m, k, v)
        for c in range(fch, fch + cc):
            put_kv(m, flat[c][0], build(c))
        return m

    print(f"BUILD A PARTIR DE {buf}\n{build(0)}")
    return build(0)


def parse_blk(data: bytes, _debug: bool = False) -> Optional[dict]:
    """Dispatcher BLK selon le premier octet de tag."""
    if not data:
        return None
    tag = data[0]
    if _debug:
        print(f"  [BLK] tag=0x{tag:02x}  len={len(data)}", file=sys.stderr)

    if tag == 0x01:
        try:
            r = parse_fat_blk(data[1:])
            if _debug:
                keys = list(r.keys())[:8] if r else []
                print(f"  [BLK] FAT OK  root_keys={keys}", file=sys.stderr)
            return r
        except Exception as e:
            if _debug:
                print(f"  [BLK] FAT error: {e}", file=sys.stderr)
            return None

    elif tag == 0x02:
        try:
            import zstandard as zstd
        except ImportError:
            print("  [!] pip install zstandard requis pour les BLK FAT_ZSTD", file=sys.stderr)
            return None
        try:
            l = (data[1] << 16) | (data[2] << 8) | data[3]
            raw_zstd = data[4 : 4 + l]
            if _debug:
                print(f"  [BLK] FAT_ZSTD compressed={l}B avail={len(raw_zstd)}B", file=sys.stderr)
            dec = zstd.ZstdDecompressor().decompress(raw_zstd)
            if _debug:
                print(f"  [BLK] FAT_ZSTD decompressed={len(dec)}B inner_tag=0x{dec[0]:02x}", file=sys.stderr)
            if dec[0] != 0x01:
                if _debug:
                    print(f"  [BLK] FAT_ZSTD inner tag 0x{dec[0]:02x} non supporte", file=sys.stderr)
                return None
            r = parse_fat_blk(dec[1:])
            if _debug:
                keys = list(r.keys())[:8] if r else []
                print(f"  [BLK] FAT_ZSTD OK  root_keys={keys}", file=sys.stderr)
            return r
        except Exception as e:
            if _debug:
                print(f"  [BLK] FAT_ZSTD error: {e}", file=sys.stderr)
            return None

    elif tag == 0x03:
        if _debug:
            print("  [BLK] SLIM (0x03) non supporte sans name map", file=sys.stderr)
        return None

    elif tag == 0x04:
        if _debug:
            print("  [BLK] SLIM_ZSTD (0x04) non supporte sans name map", file=sys.stderr)
        return None

    if _debug:
        print(f"  [BLK] tag inconnu 0x{tag:02x}", file=sys.stderr)
    return None


# =============================================================================
# 6. EXTRACTION DES JOUEURS DEPUIS LE SETTINGS BLK
# =============================================================================

@dataclass
class PlayerFromSettings:
    """Données statiques présentes dès le header du replay."""
    slot:         int            # index dans mplace (0-based)
    name:         str
    clan_tag:     str
    user_id:      int
    team:         int            # 1 = équipe A, 2 = équipe B, 0 = unknown
    vehicle:      str            # shortname du véhicule principal
    country:      str            # nation (usa, ussr, germany, …)
    rank:         int
    exp:          int


def _get_str(d, *keys) -> str:
    """Navigue dans un dict BLK et retourne le premier champ trouvé, en str."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return str(v)
    return ""


def _get_int(d, *keys) -> int:
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    return 0


def debug_blk_structure(d, prefix="", max_depth=6, _depth=0):
    """
    Affiche récursivement toutes les clés/valeurs d'un dict BLK.
    Utile pour découvrir la structure exacte d'un replay inconnu.
    Appelé avec --debug-blk.
    """
    if _depth > max_depth or not isinstance(d, dict):
        return
    for k, v in d.items():
        if isinstance(v, dict):
            print(f"{prefix}{k}/")
            debug_blk_structure(v, prefix + "  ", max_depth, _depth + 1)
        elif isinstance(v, list):
            # Affiche le premier élément comme représentant
            sample = v[0] if v else None
            if isinstance(sample, dict):
                print(f"{prefix}{k}[]  ({len(v)} entrées)")
                debug_blk_structure(sample, prefix + "  [0]/", max_depth, _depth + 1)
            else:
                print(f"{prefix}{k}[]  = {v[:3]}{'...' if len(v) > 3 else ''}")
        else:
            # Tronque les longues valeurs
            sv = str(v)
            print(f"{prefix}{k} = {sv[:80]}{'…' if len(sv) > 80 else ''}")


def _find_list_in_blk(d: dict, *candidate_keys) -> list:
    """
    Cherche un nœud liste dans le dict BLK en testant plusieurs noms de clé.
    Gère les cas où la valeur est un dict unique (un seul enfant → pas de liste).
    """
    for key in candidate_keys:
        val = d.get(key)
        if val is None:
            continue
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            return [val]
    return []


def _extract_vehicle_from_slot(slot_node: dict) -> tuple[str, str, int]:
    """
    Retourne (vehicle_name, country, rank) depuis un nœud slot BLK.

    Stratégie multi-passes :
    1. Cherche un sous-nœud aircraft/vehicle/unit/plane/tank/ship
    2. Si plusieurs véhicules (liste), prend le premier
    3. Cherche directement les champs sur le slot (parfois pas de sous-nœud)
    """
    # Clés de sous-nœud possibles selon la version du jeu
    for key in ('aircraft', 'vehicle', 'unit', 'plane', 'tank', 'ship', 'helicopter'):
        sub = slot_node.get(key)
        if sub is None:
            continue
        # Peut être une liste (plusieurs véhicules en réserve)
        if isinstance(sub, list):
            sub = sub[0] if sub else None
        if isinstance(sub, dict):
            v = _get_str(sub, 'name', 'shortName', 'unitName', 'id')
            c = _get_str(sub, 'country', 'nation', 'countryId')
            r = _get_int(sub, 'rank', 'tier', 'battleRating')
            if v:
                return v, c, r

    # Fallback : champs véhicule directement sur le slot
    v = _get_str(slot_node, 'unitName', 'vehicleName', 'aircraftName', 'tankName')
    print(f"VEHICLE FROM SLOT:        {v}")
    c = _get_str(slot_node, 'country', 'nation')
    r = _get_int(slot_node, 'rank', 'tier')
    return v, c, r


def extract_players_from_settings(settings: dict) -> list['PlayerFromSettings']:
    """
    Extrait la liste des joueurs depuis le Settings BLK.

    Le format du Settings BLK a varié selon les versions de War Thunder.
    Cette fonction est volontairement tolérante et explore plusieurs chemins.

    Structures observées :
        Version ancienne :
            root → mplace[] → { name, clanTag, userId, team, aircraft{} }

        Version récente :
            root → mplace[] → { name, clanTag, userId, team, aircraft[] }
            (plusieurs véhicules de réserve par joueur)

        Parfois le nœud s'appelle 'player', 'slot', 'member' selon la version.
        Parfois aircraft est directement dans le slot sans sous-nœud.
    """
    players = []
    if not settings:
        return players

    # Cherche le nœud liste des joueurs — par ordre de priorité
    mplace_list = _find_list_in_blk(
        settings,
        'mplace', 'player', 'slot', 'member', 'participants'
    )

    if not mplace_list:
        # Dernier recours : cherche n'importe quelle liste de dicts avec un champ 'name'
        for key, val in settings.items():
            candidates = val if isinstance(val, list) else ([val] if isinstance(val, dict) else [])
            if candidates and isinstance(candidates[0], dict) and 'name' in candidates[0]:
                mplace_list = candidates
                break

    for i, slot in enumerate(mplace_list):
        if not isinstance(slot, dict):
            continue

        name     = _get_str(slot, 'name', 'playerName', 'nick', 'userName')
        clan_tag = _get_str(slot, 'clanTag', 'clan', 'clanName', 'clanId')
        user_id  = _get_int(slot, 'userId', 'uid', 'userID', 'playerId')
        team     = _get_int(slot, 'team', 'teamId', 'side')

        vehicle, country, rank = _extract_vehicle_from_slot(slot)
        ac_node = slot.get('aircraft') or slot.get('vehicle') or {}
        if isinstance(ac_node, list):
            ac_node = ac_node[0] if ac_node else {}
        if not isinstance(ac_node, dict):
            ac_node = {}
        exp = _get_int(ac_node, 'exp', 'experience', 'xp')

        players.append(PlayerFromSettings(
            slot=i, name=name, clan_tag=clan_tag, user_id=user_id,
            team=team, vehicle=vehicle, country=country, rank=rank, exp=exp,
        ))

    return players


# =============================================================================
# 7. PARSER SLOT — PLAYERINIT (packetslot/main.go)
# =============================================================================

# Signatures des paquets MPI contenant des slot messages
SLOT_SIGS = [
    bytes([0x02, 0x58, 0xaa, 0xff]),
    bytes([0x02, 0x58, 0x2d, 0xf0]),
]


@dataclass
class PlayerFromSlot:
    """Données dynamiques extraites des paquets Slot durant la partie."""
    slot:     int           # index 0-255
    time_ms:  int
    user_id:  int
    name:     str
    clan_tag: str
    title:    str


def _parse_slot_player_init(slot: int, time_ms: int, msg: bytes) -> Optional['PlayerFromSlot']:
    """
        ParseSlotMessage_PlayerInit (packetslot/main.go).
        Format après le header de 5 octets :
            u32  UserID
            u32  Unk0          (doit être 0)
            [64] Name          (null-padded)
            [20] skip
            lenstr ClanTag
            lenstr Title
        """
    try:
        # Vérification du header de 5 octets
        if len(msg) < 5:
            return None
        if msg[0] != 0x70 or msg[4] != 0x60:
            return None
        if msg[3] not in (0x08, 0x30):
            return None
        if msg[2] not in (0x01, 0x02):
            return None

        offset = 5

        # Lire UserID et Unk0
        if offset + 8 > len(msg):
            return None

        #print(f"MESSAGE PLAYER         :{msg}")
        user_id, = struct.unpack_from('<I', msg, offset)
        offset += 4
        unk0, = struct.unpack_from('<I', msg, offset)
        offset += 4
        if unk0 != 0:
            return None

        # Lire le nom du joueur (64 octets, null-padded)
        if offset + 64 > len(msg):
            return None
        raw_name = msg[offset:offset + 64]
        name = raw_name.rstrip(b'\x00').decode('utf-8', errors='replace')
        offset += 64

        # Skip 20 octets
        offset += 20

        # Lire le nom redondant et extraire le clan_tag
        clan_tag = ""

        if offset < len(msg):
            len_nom_redondant = msg[offset]
            offset += 1
            if len_nom_redondant > 0:
                if offset + len_nom_redondant > len(msg):
                    return None
                nom_redondant_bytes = msg[offset:offset + len_nom_redondant]
                nom_redondant = nom_redondant_bytes.decode('utf-8', errors='replace')

                lines = nom_redondant.splitlines()

                # Trouver l'index de "Bot"
                bot_line_index = -1
                for i, line in enumerate(lines):
                    if "Bot" in line:
                        bot_line_index = i
                        break

                if bot_line_index != -1 and len(lines) > bot_line_index:
                    # La ligne suivant celle contenant "Bot" est le clan_tag
                    clan_tag_line = lines[bot_line_index + 1]

                    # Trouver la fin du clan_tag (avant \x00)
                    end_index = clan_tag_line.find('\x00')



                    if end_index != -1:
                        clan_tag = clan_tag_line[:end_index]
                    else:
                        clan_tag = clan_tag_line
                else:
                    # Si "Bot" n'est pas trouvé, vérifier si c'est un tag de clan
                    if len(nom_redondant) <= 10:  # Longueur typique d'un tag de clan
                        clan_tag = nom_redondant

                # Nettoyer les caractères spéciaux du clan_tag
                if clan_tag:
                    # Supprimer les caractères non imprimables et les caractères spéciaux indésirables
                    if len(clan_tag) > 0 and not clan_tag[0].isalnum():
                        clan_tag = clan_tag[1:]

                    # Supprimer le dernier caractère s'il n'est pas une lettre ou un chiffre
                    if len(clan_tag) > 0 and not clan_tag[-1].isalnum():
                        clan_tag = clan_tag[:-1]

                    #print(f"CLAN_TAG (nettoyé)  :{clan_tag}")

                offset += len_nom_redondant


        return PlayerFromSlot(slot=slot, time_ms=time_ms, user_id=user_id,
                              name=name, clan_tag=clan_tag, title="")

    except Exception as e:
        print(f"Erreur lors du parsing: {e}")
        return None


def parse_slot_packet(pk: RawPacket, _dump_unknown: bool = False) -> list:
    """
    Parse un paquet MPI slot (signatures 02 58 aa ff / 02 58 2d f0).
    Retourne la liste des PlayerFromSlot trouvés dans ce paquet.
    Si _dump_unknown=True, ajoute aussi les messages non-reconnus (str) pour analyse.
    """
    results = []
    if len(pk.payload) < 4:
        return results
    if pk.payload[:4] not in SLOT_SIGS:
        return results

    try:
        buf = pk.payload[4:]
        pos = 0

        # Octet data_compressed
        data_compressed = buf[pos]; pos += 1

        if data_compressed > 0:
            # Octet unk0
            pos += 1
            control = buf[pos]; pos += 1
            pos += 2  # unk1 (2 octets)
            if control & 0xF0:
                pos += 1  # unk2 (parfois présent si blk type slim)

            # Décompression zstd (magic 28b52ffd)
            try:
                import zstandard as zstd
                raw = buf[pos:]
                decompressed = zstd.ZstdDecompressor().decompress(raw)
                inner = io.BytesIO(decompressed)
            except ImportError:
                print("  [!] pip install zstandard requis pour les paquets Slot compressés",
                      file=sys.stderr)
                return results
            except Exception:
                return results
        else:
            inner = io.BytesIO(buf[pos:])

        # Lecture du nombre de messages (u16 LE)
        msg_count_bytes = inner.read(2)
        if len(msg_count_bytes) < 2:
            return results
        message_count, = struct.unpack_from('<H', msg_count_bytes)

        for _ in range(message_count):
            # Longueur du message (u16 LE)
            ml_bytes = inner.read(2)
            if len(ml_bytes) < 2:
                break
            msg_len, = struct.unpack_from('<H', ml_bytes)
            # Premier octet = slot
            slot_byte = inner.read(1)

            if not slot_byte:
                break
            slot = slot_byte[0]
            # Reste du message (msg_len - 1)

            msg_body = inner.read(msg_len - 1)
            if len(msg_body) < msg_len - 1:
                break

            player = _parse_slot_player_init(slot, pk.current_time, msg_body)

            if player:
                results.append(player)
            elif _dump_unknown and len(msg_body) >= 5:
                # Log les messages non-reconnus pour analyse du spawn event
                h = msg_body[:5].hex()
                body_preview = msg_body[5:37].hex() if len(msg_body) > 5 else ""
                results.append(f"UNKNOWN slot={slot} t={pk.current_time}ms "
                               f"hdr={h} body={body_preview}")

    except Exception:
        pass

    return results



# =============================================================================
# 8b. SCANNER MPI — identifie toutes les signatures type 4 inconnues
# =============================================================================

# Signatures de paquets type 4 déjà traités — tout le reste est "inconnu"
_KNOWN_MPI_SIGS: set[bytes] = {
    bytes([0x02, 0x58, 0x58, 0xf0]),  # Kill
    bytes([0x02, 0x58, 0x78, 0xf0]),  # Award
    bytes([0x02, 0x58, 0xaa, 0xff]),  # Slot message
    bytes([0x02, 0x58, 0x2d, 0xf0]),  # Slot message variante
    bytes([0x02, 0x58, 0x22, 0xf0]),  # Compressed blobs
}

@dataclass
class MpiSignature:
    sig:       bytes     # 4 premiers octets
    count:     int       # nombre d'occurrences
    sizes:     list      # tailles des payloads observées (dédupliqué)
    examples:  list      # jusqu'à 5 exemples : (time_ms, payload[:48])


def scan_mpi_signatures(paths: list[str], max_examples: int = 5) -> dict[bytes, MpiSignature]:
    """
    Lit tous les fichiers .wrpl et collecte les signatures des paquets MPI
    (type 4) non reconnus. Retourne un dict sig_bytes → MpiSignature.
    Outil de rétro-ingénierie pour identifier le spawn event et autres
    paquets inconnus.
    """
    from collections import defaultdict
    results: dict[bytes, MpiSignature] = {}

    for path in paths:
        try:
            data   = Path(path).read_bytes()
            header = parse_header(data)
        except Exception:
            continue

        decompressed = _decompress_packet_stream(data, header)
        if not decompressed:
            continue

        stream = io.BytesIO(decompressed)
        for pk in read_packets(stream):
            if pk.packet_type != 4 or len(pk.payload) < 4:
                continue

            sig4 = pk.payload[:4]

            # Ignore les signatures connues
            if sig4 in _KNOWN_MPI_SIGS:
                continue
            # Ignore aussi les movement packets (détectés par conditions)
            if _matches(pk.payload, MOVEMENT_CONDITIONS):
                continue

            if sig4 not in results:
                results[sig4] = MpiSignature(sig4, 0, [], [])

            entry = results[sig4]
            entry.count += 1
            sz = len(pk.payload)
            if sz not in entry.sizes:
                entry.sizes.append(sz)
            if len(entry.examples) < max_examples:
                entry.examples.append((pk.current_time, pk.payload[:64]))

    return results


def print_mpi_scan(results: dict[bytes, MpiSignature], top: int = 30) -> None:
    """Affiche les résultats du scan MPI de façon lisible."""
    if not results:
        print("  Aucune signature inconnue trouvée.")
        return

    #print(f"  {len(results)} signatures distinctes :")
    # Trie par fréquence décroissante
    for sig, entry in sorted(results.items(), key=lambda x: -x[1].count)[:top]:
        hex_sig = sig.hex()
        sizes_str = str(sorted(set(entry.sizes))[:6])
        print(f"  sig={hex_sig}  count={entry.count:>6}  sizes={sizes_str}")
        # Affiche le premier exemple pour voir la structure
        if entry.examples:
            t_ms, payload = entry.examples[0]
            print(f"    exemple t={t_ms}ms  payload[0:64]={payload.hex()}")
            # Essaie de deviner si ça ressemble à slot+lenstr
            if len(payload) >= 6:
                potential_slot = payload[4]
                potential_len  = payload[5]
                if 1 <= potential_len <= 40 and 6 + potential_len <= len(payload):
                    potential_str = payload[6 : 6 + potential_len]
                    if all(32 <= b < 127 for b in potential_str):
                        print(f"    → potentiel slot={potential_slot} "
                              f"string='{potential_str.decode()}'")

# =============================================================================
# 8. PARSERS PAQUETS SPÉCIALISÉS (type 3 / 4 / 6)
# =============================================================================

# --- Chat Message (type 4) ---

@dataclass
class ChatMessage:
    seq:          int
    time_ms:      int
    sender:       str
    content:      str
    channel_type: int
    is_enemy:     int


def parse_chat(pk: RawPacket) -> Optional[ChatMessage]:
    try:
        d = pk.payload
        sender,  off = read_lenstr(d, 0)
        content, off = read_lenstr(d, off)
        return ChatMessage(pk.seq, pk.current_time, sender, content,
                           d[off], d[off + 1])
    except Exception:
        return None


# --- Kill (type 4, sig 02 58 58 f0) ---

KILL_SIG = bytes([0x02, 0x58, 0x58, 0xf0])


@dataclass
class KillEntry:
    seq:             int
    time_ms:         int
    damage_type:     int   # control & 0xF0 : 0x10=AP, 0x20=APHE, 0x30=HEAT, 0x40=HE/Frag
    killer_slot:     int
    killer_vehicle:  str
    victim_slot:     int   # -1 si non déterminé
    victim_vehicle:  str
    remainder_hex:   str


def parse_kill(pk: RawPacket) -> Optional[KillEntry]:
    if len(pk.payload) < 4 or pk.payload[:4] != KILL_SIG:
        return None
    try:
        #print(f"PARSE KILLS DATA       :{pk}")
        d = pk.payload[4:]
        control     = d[0]
        damage_type = control & 0xF0
        killer_slot = d[4]
        killer_vehicle, off = read_lenstr(d, 8)
        # Remainder : victim_slot(1B) + 3B skip + victim_vehicle(lenstr)
        victim_slot    = -1
        victim_vehicle = ""
        rem = d[off:]
        if len(rem) >= 5:
            victim_slot = rem[0]
            vv_len      = rem[4]
            if len(rem) >= 5 + vv_len:
                victim_vehicle = rem[5 : 5 + vv_len].decode("utf-8", errors="replace")
                rem = rem[5 + vv_len:]
            else:
                rem = rem[1:]
        remainder = rem.hex()
        return KillEntry(pk.seq, pk.current_time, damage_type,
                         killer_slot, killer_vehicle,
                         victim_slot, victim_vehicle, remainder)
    except Exception:
        return None


# --- Award (type 4, sig 02 58 78 f0) ---

AWARD_SIG = bytes([0x02, 0x58, 0x78, 0xf0])


@dataclass
class Award:
    seq:        int
    time_ms:    int
    award_type: int
    player_slot: int
    award_name: str


def parse_award(pk: RawPacket) -> Optional[Award]:
    if len(pk.payload) < 4 or pk.payload[:4] != AWARD_SIG:
        return None
    try:
        d = pk.payload[4:]
        award_type  = d[0]
        # 2 octets (Always0x003E)
        player_slot = d[3]
        # 3 octets (Always0x000000)
        name, _ = read_lenstr(d, 7)
        return Award(pk.seq, pk.current_time, award_type, player_slot, name)
    except Exception:
        return None

def _update_win_team(stats: list['PlayerStats'], awards: list[Award]) -> list['PlayerStats']:

    for award in awards:
        if award.award_name == 'hidden_win_streak':
            for stat in stats:
                if stat.slot == award.player_slot:
                    stat.is_winner = True


    return stats


# --- Movement (type 4, conditions multiples) ---

MOVEMENT_CONDITIONS = {0: 0xff, 1: 0x0f, 5: 0xa3, 6: 0xf0, 10: 0x00, 11: 0x00, 13: 0x14}


@dataclass
class EntityMovement:
    seq:     int
    time_ms: int
    eid:     int
    x:       float
    y:       float
    z:       float


def _matches(payload: bytes, cond: dict) -> bool:
    return all(i < len(payload) and payload[i] == v for i, v in cond.items())


def parse_movement(pk: RawPacket) -> Optional[EntityMovement]:
    if len(pk.payload) < 40 or not _matches(pk.payload, MOVEMENT_CONDITIONS):
        return None
    try:
        first16 = struct.unpack_from('<H', pk.payload, 2)[0]
        if first16 & 1:
            eid = (first16 >> 2) | (((first16 & 2) >> 1) << 22)
        elif first16 & 2:
            eid = (first16 >> 2) | (pk.payload[4] << 22)
        else:
            second16 = struct.unpack_from('<H', pk.payload, 4)[0]
            raw = (second16 << 16) | first16
            eid = ((raw & 0x00ffffff) >> 2) | ((raw >> 24) << 22)
        x = struct.unpack_from('<d', pk.payload, 14)[0]
        y = struct.unpack_from('<d', pk.payload, 22)[0]
        z = struct.unpack_from('<d', pk.payload, 30)[0]
        return EntityMovement(pk.seq, pk.current_time, eid, x, y, z)
    except Exception:
        return None


# --- Player Vehicle Verification (type 6) ---

@dataclass
class PlayerVehicle:
    seq:               int
    slot:              int
    vehicle_id:        str | None = None
    vehicle_name:      str | None = None
    country:           str | None = None
    vehicle_type:      str | None = None
    vehicle_br:        int | None = None
    image_path:        str | None = None

IDX_PLAYERS_NUM = [b'01_', b'O1_', b'02_', b'O2_', b'03_', b'O3_', b'04_', b'O4_', b'05_', b'O5_', b'06_', b'O6_',
                   b'07_', b'O7_', b'08_', b'O8_', b'09_', b'O9_', b'10_', b'11_', b'12_', b'13_', b'14_', b'15_',
                   b'16_']

def _matches_pk(pk: RawPacket) -> bool:
    """Vérifie si le payload correspond au pattern ECS type 6."""
    d = pk.payload

    # Vérification de longueur minimale
    if len(d) < 6:
        return False

    # Premier byte doit être '%' (0x25)
    if d[0] != ord('%'):
        return False

    # Vérifier la présence de 'rt1_' dans le payload
    if b'\rt1_' not in d:
        return False

    return True

def calcul_br_season() -> float | None:
    from database.db_informations import InformationDB
    from datetime import datetime

    year = datetime.now().year
    month = datetime.now().month

    season_num = int(month / 2) if not int(month % 2) else math.ceil(month / 2)

    db_sqb = InformationDB()
    br_season = db_sqb.get_schedular_for_season(year=year, season_num=season_num)
    if not br_season:
        return None

    for br, dates in br_season:
        date_debut = datetime.strptime(dates[0], "%d/%m/%Y")
        date_fin = datetime.strptime(dates[1], "%d/%m/%Y")

        if date_debut <= datetime.now() <= date_fin:
            return float(br)
        else:
            print("[PlayerVehicle] [!]     calcul_br_season() - Erreur lors de la récupération du BR")

    return None

def _vehicles_filter(vehicles: dict, names_vehicles: list) -> dict[str, VehicleInfo]:
    """
    Filtre un dictionnaire de véhicules selon une liste de noms et un seuil de BR.

    :param vehicles: Le dictionnaire de véhicules à filtrer.
    :param names_vehicles: Liste des noms de véhicules (clés) à conserver.

    :returns: Un nouveau dictionnaire filtré.
    """
    seuil_br = None #calcul_br_season()
    filter = {}

    if not seuil_br:
        for name in names_vehicles:
            if name in vehicles:
                vehicle = vehicles[name]

                if isinstance(vehicle, VehicleInfo):
                    filter[name] = vehicle
        print(f"FILTER    :{filter}")
        return filter

    for name in names_vehicles:
        if name in vehicles:
            vehicule = vehicles[name]
            if isinstance(vehicule, dict) and 'realistic_ground_br' in vehicule:
                if vehicule['realistic_ground_br'] <= seuil_br:
                    filter[name] = vehicule.copy()

    return filter

def _search_unfound_slot(vehicles_players_dict: dict) -> list | None:
    list_of_slot = vehicles_players_dict.keys()
    slot_unfound = []

    if len(list_of_slot) == 16:
        return None

    for i in range(0, 16):
        if i not in list_of_slot:
            slot_unfound.append(i)

    return slot_unfound

def _search_slot(pk: RawPacket) -> tuple:
    '''
    Extrait le numéro de slot du payload ECS type 6.

    Formats possibles après 'rt1_' :
      - rt1_playerXX_0 (ex: rt1_player08_0 → slot = 7)
      - rt1_\x01\\XX   (ex: rt1_;\x01\\05 → slot = 4)

    :param pk: RawPacket
    :return: list[int [0;255], int | None] -> La valeur de slot attribué au joueur sinon -1 si aucune valeur | Soit int pour
    rt1_ soit None si index inférieur à 0
    '''
    d = pk.payload

    #print(f"VEHICLE SLOT PLAYER ELSE [modifié par moi]:      {d}")

    #cherche l'offest où se trouve rt1_
    rt1_idx = d.find(b'\rt1_')
    else_idx = d.find(b'_0')

    if rt1_idx < 0:
        return -1, None
    elif else_idx < 0:
        return -1, None

    # Extraire les octets suivants (jusqu'à 20 octets pour sécurité)
    if rt1_idx:
        context = d[rt1_idx + 4: min(rt1_idx + 25, len(d))]
        #print(f"VEHICLE SLOT PLAYER [modifié par moi]:      {d[rt1_idx - 20: min(rt1_idx + 25, len(d))]}")
    elif else_idx:
        context = d[else_idx + 4: min(rt1_idx + 25, len(d))]
    else:
        return -1, None

    #print(f"VEHICLE SLOT PLAYER [vue par bot]:      {context}")

    try:
        # Format 1 : playerXX (ex: player05)
        if b'player' in context:
            match = re.search(rb'player(\d{2})', context)
            if match:
                slot_str = match.group(1).decode('utf-8')

                return int(slot_str) - 1, rt1_idx

        # Format 2 (NOUVEAU) : rt1_ avec chiffres décalés (ex: \rt1_...T11_0)
        # On cherche 'rt1_' puis on cherche n'importe quoi jusqu'à trouver deux chiffres
        elif b'T' in context:
            # Cette regex cherche 'rt1_', puis saute les caractères non-chiffres (.*?)
            # pour capturer les deux premiers chiffres trouvés (\d{2})
            match = re.search(rb'T(\d{2})', context)
            if match:
                slot_str = match.group(1).decode('utf-8')
                return int(slot_str) - 1, rt1_idx

        # Format 3 : ;\x01\\XX (backslash + chiffres après \x01)
        elif b';\x01' in context:
            match = re.search(rb'[\\](\d{2})', context)
            if match:
                slot_str = match.group(1).decode('utf-8')
                return int(slot_str) - 1, rt1_idx

        # Format 4 : Chiffres directs (ex: rt1_05_)
        elif b'rt1_' in context:
            match = re.search(rb'rt1_(\d{2})', context)
            if match:
                slot_str = match.group(1).decode('utf-8')
                return int(slot_str) - 1, rt1_idx

        # Format 5 : Chiffres directs (ex: 05)
        else:
            match = re.search(rb'(\d{2})', context)
            if match:
                slot_str = match.group(1).decode('utf-8')
                return int(slot_str) - 1, rt1_idx

    except Exception as e:
        print(f"[PlayerVehicle] [!] Search slot : {e}", file=sys.stderr)

    return -1, None

def _search_vehicle_check(pk: RawPacket, vehicle_db: dict | None, lineup_per_players: dict) -> list[PlayerVehicle] | list:
    '''
    Extrait le numéro de slot du payload ECS type 6.

    Formats possibles après 'rt1_' :
      - rt1_playerXX_0 (ex: rt1_player08_0 → slot = 7)
      - rt1_\x01\\XX   (ex: rt1_;\x01\\05 → slot = 4)

    :param pk: RawPacket
    :return: list[int [0;255], int | None] -> La valeur de slot attribué au joueur sinon -1 si aucune valeur | Soit int pour
    rt1_ soit None si index inférieur à 0
    '''

    '''
    TODO: Ajouter une vérification par rapport aux BR de la saison, pour ajouter un paramètre de vérification, 
    ça enlevera des erreurs possibles => exemple si 
    CLEAN NAME:      tiger
    CLEAN NAME:      germ_sturmmorser
    
    PlayerVehicle(seq=1279, slot=0, vehicle_id='tiger_uht', vehicle_name='EC-665 Tiger UHT', country='germany', 
    vehicle_type='H', vehicle_br=12.7, image_path='images/vehicles/tiger_uht.png')
    &&
    PlayerVehicle(seq=1279, slot=0, vehicle_id='germ_sturmmorser_sturmtiger', vehicle_name='38 cm Sturmmörser', 
    country='germany', vehicle_type='T', vehicle_br=5.7, image_path='images/vehicles/germ_sturmmorser_sturmtiger.png')
    
    et la partie à eut lieu au BR 7.3, donc Tiger impossible !
    
    +++ 
    
    Ajouter la liste différents véhicules dans la lineup de chaque team pour accentuer la précision. 
    
    il doit y etre dans PlayerFromSlot []
    '''
    FORBIDDEN_STRINGS = {
        "camo_", "_long", "superstructure", "birch",
        "slotId", "_body", "_default"
    }

    FORBIDDEN_CHARS = {'+', '~', '#', '=', '%', '|', '{', '}', ';', '<', '>'}

    d = pk.payload

    if not vehicle_db:
        print("[PlayerVehicle] [!] vehicle_db is empty")
        return []

    vehicle_ids = list(vehicle_db.keys())

    parts = [p for p in re.findall(b'[ -~]+', d) if len(p) >= 2]
    matched_prefix = []
    vehicles_players = []

    """indices_pattern = b'|'.join([re.escape(p) for p in IDX_PLAYERS_NUM])

    # Explication du groupe de préfixe : (?:rt1|[tT]1|[tT]|)
    # - rt1 : cherche exactement rt1
    # - [tT]1 : cherche t1 ou T1
    # - [tT]  : cherche t ou T tout seul
    # - |     : ou rien du tout (vide)
    pattern = re.compile(b'(?:rt1|[tT]1|[tT]|)(?:' + indices_pattern + b')(?:player|0|$)')
    """

    # On définit uniquement ce qui est l'INDEX (le cœur du problème)
    # On cherche : une lettre optionnelle + un nombre entre 1 et 16 + un underscore
    # Le pattern ne s'occupe plus de chercher "player" ou "0", il cherche juste l'index.
    index_pattern = re.compile(b'[a-zA-Z]?(?:1[0-6]|[1-9])_0')

    """for i, part in enumerate(parts):
        match = pattern.search(part)
        if match:
            for prefix in IDX_PLAYERS_NUM:
                if prefix in match.group(0):
                    matched_prefix.append((i, prefix))"""

    for i, part in enumerate(parts):
        match = index_pattern.search(part)

        #print(f"PART   : {part.decode('utf-8', errors='ignore')} | Matches found: {match}")

        if match:
            # On a trouvé un index (ex: b't1_', b'14_', b'K5_')
            full_match = match.group(0)
            print(f"FULL MATCH   : {full_match}")

            matched_prefix.append((i, full_match))



    #print(f"MATCHED PREFIX:      {matched_prefix}")

    if matched_prefix:
        for idx, prefix_found in matched_prefix:
            digit_match = re.search(rb'\d+', prefix_found)
            if not digit_match:
                continue

            slot_str = digit_match.group().decode('utf-8')
            slot = int(slot_str) - 1

            search_range = parts[idx - 4:idx] if idx >= 4 else parts[0:idx]
            search_range = search_range[::-1]

            #print(f"SEARCH RANGE:      {search_range}")

            for possible_vehicle in search_range:
                try:
                    clean_name = possible_vehicle.rpartition(b'/')[-1].decode("utf-8", errors="ignore")
                except Exception:
                    continue

                if any(forbidden in clean_name for forbidden in FORBIDDEN_STRINGS):
                    continue

                if any(char in clean_name for char in FORBIDDEN_CHARS):
                    continue

                #print(f"CLEAN NAME:      {clean_name}")

                best_match_for_this_part = None

                """# Recherche dans la DB
                for vid, vehicle_obj in vehicle_db.items():
                    # On vérifie si le nom propre est contenu dans l'ID de la DB (ou inversement)

                    if vid in clean_name:
                        # On cherche le match le plus long pour éviter les faux positifs (ex: 'm4' vs 'amx_m4')
                        if len(vid) > max_length:
                            max_length = len(vid)
                            best_match_for_this_part = vehicle_obj"""

                matches = difflib.get_close_matches(clean_name, vehicle_ids, n=1, cutoff=0.7)
                if matches:
                    matched_id = matches[0]

                    check_match = lineup_per_players.get(slot)
                    #print(f"CHECK MATCH        :{check_match}")

                    #K5_0 => correspond pas que à 5
                    if matched_id in check_match:
                        best_match_for_this_part = vehicle_db[matched_id]

                # Si on a trouvé un véhicule pour ce segment précis
                if best_match_for_this_part:
                    vehicles_players.append(
                        PlayerVehicle(
                            seq=pk.seq,
                            slot=slot,
                            vehicle_id=getattr(best_match_for_this_part, 'id', None),
                            vehicle_name=getattr(best_match_for_this_part, 'display_name', None),
                            country=getattr(best_match_for_this_part, 'country', None),
                            vehicle_type=getattr(best_match_for_this_part, 'vehicle_type', None),
                            image_path=getattr(best_match_for_this_part, 'image_path', None),
                            vehicle_br=getattr(best_match_for_this_part, 'br', None)
                        )
                    )


    return vehicles_players


def _double_check_vehicle(
        pk: RawPacket, vehicle_db: dict | None, lineup_per_players: dict, unfound_slot: list
) -> list[PlayerVehicle] | list:
    '''
    Revérifie les slots non trouvés dans les paquets.

    :param pk: Contient une liste de bytes
    :param vehicle_db: dict | None
    :param lineup_per_players: dict | None
    :param unfound_slot: list | None

    :return: list[int [0;255], int | None] -> La valeur de slot attribué au joueur sinon -1 si aucune valeur | Soit int pour
    rt1_ soit None si index inférieur à 0
    '''

    FORBIDDEN_STRINGS = {
        "camo_", "_long", "superstructure", "birch",
        "slotId", "_body", "_default"
    }

    FORBIDDEN_CHARS = {'+', '~', '#', '=', '%', '|', '{', '}', ';', '<', '>'}

    d = pk.payload

    if not vehicle_db:
        print("[PlayerVehicle] [!] vehicle_db is empty")
        return []

    vehicle_ids = list(vehicle_db.keys())

    parts = [p for p in re.findall(b'[ -~]+', d) if len(p) >= 2]
    matched_prefix = []
    vehicles_players = []

    """indices_pattern = b'|'.join([re.escape(p) for p in IDX_PLAYERS_NUM])

    # Explication du groupe de préfixe : (?:rt1|[tT]1|[tT]|)
    # - rt1 : cherche exactement rt1
    # - [tT]1 : cherche t1 ou T1
    # - [tT]  : cherche t ou T tout seul
    # - |     : ou rien du tout (vide)
    pattern = re.compile(b'(?:rt1|[tT]1|[tT]|)(?:' + indices_pattern + b')(?:player|0|$)')
    """

    # On définit uniquement ce qui est l'INDEX (le cœur du problème)
    # On cherche : une lettre optionnelle + un nombre entre 1 et 16 + un underscore
    # Le pattern ne s'occupe plus de chercher "player" ou "0", il cherche juste l'index.
    index_pattern = re.compile(b'[a-zA-Z]?(?:1[0-6]|[1-9])_0')

    """for i, part in enumerate(parts):
        match = pattern.search(part)
        if match:
            for prefix in IDX_PLAYERS_NUM:
                if prefix in match.group(0):
                    matched_prefix.append((i, prefix))"""

    for i, part in enumerate(parts):
        match = index_pattern.search(part)

        #print(f"PART RECHECK  : {part.decode('utf-8', errors='ignore')} | Matches found: {match}")

        if match:
            # On a trouvé un index (ex: b't1_', b'14_', b'K5_')
            full_match = match.group(0)
            digit_match = re.search(rb'\d+', full_match)
            slot_str = digit_match.group().decode('utf-8')
            slot = int(slot_str) - 1

            for j in unfound_slot:
                if j % 10 == slot:
                    matched_prefix.append((i, j))

                    #print(f"DIGIT MATCH RECHECK      : {(i, j)}")



    #print(f"MATCHED PREFIX RECHECK:      {matched_prefix}")

    if matched_prefix:
        for idx, slot in matched_prefix:

            search_range = parts[idx - 4:idx] if idx >= 4 else parts[0:idx]
            search_range = search_range[::-1]

            #print(f"SEARCH RANGE RECHECK:      {search_range}")

            for possible_vehicle in search_range:
                try:
                    clean_name = possible_vehicle.rpartition(b'/')[-1].decode("utf-8", errors="ignore")
                except Exception:
                    continue

                if any(forbidden in clean_name for forbidden in FORBIDDEN_STRINGS):
                    continue

                if any(char in clean_name for char in FORBIDDEN_CHARS):
                    continue

                #print(f"CLEAN NAME RECHECK:      {clean_name}")

                best_match_for_this_part = None

                matches = difflib.get_close_matches(clean_name, vehicle_ids, n=1, cutoff=0.7)
                if matches:
                    matched_id = matches[0]

                    check_match = lineup_per_players.get(slot)

                    # K5_0 => correspond pas que à 5
                    if matched_id in check_match:
                        best_match_for_this_part = vehicle_db[matched_id]

                # Si on a trouvé un véhicule pour ce segment précis
                if best_match_for_this_part:
                    vehicles_players.append(
                        PlayerVehicle(
                            seq=pk.seq,
                            slot=slot,
                            vehicle_id=getattr(best_match_for_this_part, 'id', None),
                            vehicle_name=getattr(best_match_for_this_part, 'display_name', None),
                            country=getattr(best_match_for_this_part, 'country', None),
                            vehicle_type=getattr(best_match_for_this_part, 'vehicle_type', None),
                            image_path=getattr(best_match_for_this_part, 'image_path', None),
                            vehicle_br=getattr(best_match_for_this_part, 'br', None)
                        )
                    )
                    #print(f"BEST MATCH RECHECK       :{best_match_for_this_part}")

            if slot not in vehicles_players:
                possible_match = lineup_per_players.get(slot)
                len_match = len(possible_match)

                match len_match:
                    case 1:
                        vehicles_players.append(
                            PlayerVehicle(
                                seq=pk.seq,
                                slot=slot,
                                vehicle_id=getattr(possible_match, 'id', None),
                                vehicle_name=getattr(possible_match, 'display_name', None),
                                country=getattr(possible_match, 'country', None),
                                vehicle_type=getattr(possible_match, 'vehicle_type', None),
                                image_path=getattr(possible_match, 'image_path', None),
                                vehicle_br=getattr(possible_match, 'br', None)
                            )
                        )


    return vehicles_players


def _search_vehicle(pk: RawPacket, rt1_idx: int | None, slot: int, vehicle_db: dict | None) -> PlayerVehicle | None:
    '''
    Extrait le id du véhicule et va le chercher dans la base de données.


    :param pk: RawPacket
    :param rt1_idx: int | None
    :param vehicle_db: dict | None

    :return: list | None
    '''

    if not rt1_idx:
        print(f"[PlayerVehicle] [!] rt1_idx invalid: {rt1_idx}")
        return None

    if not vehicle_db:
        print("[PlayerVehicle] [!] vehicle_db is empty")
        return None

    d = pk.payload[:rt1_idx]  # On limite le payload à la zone utile dès le début
    best_match = None
    max_length = 0

    for vid in vehicle_db.keys():
        try:
            vid_bytes = vid.encode('utf_8')
            # Vérifie si le ID est présent dans le segment du payload
            if vid_bytes in d:
                # Si ce match est plus long que le précédent, on le mémorise
                if len(vid_bytes) > max_length:
                    max_length = len(vid_bytes)
                    best_match = vehicle_db[vid]

        except Exception as e:
            print(f"[PlayerVehicle] [!] Error: {e}", file=sys.stderr)
            continue

    if best_match:
        return PlayerVehicle(
                    seq=pk.seq,
                    slot=slot,
                    vehicle_id=getattr(best_match, 'id', None),
                    vehicle_name=getattr(best_match, 'display_name', None),
                    country=getattr(best_match, 'country', None),
                    vehicle_type=getattr(best_match, 'vehicle_type', None),
                    image_path=getattr(best_match, 'image_path', None),
                    vehicle_br=getattr(best_match, 'br', None)
                )

    print("[PlayerVehicle] [!] No vehicle found in the payload")
    return None


def parse_v_player(pk: RawPacket, vehicle_database: dict, lineup_per_players: dict) -> Any:
    try:
        if not _matches_pk(pk):
            return None

        results = []
        vehicles = _search_vehicle_check(pk, vehicle_database, lineup_per_players)

        print(f"[PlayerVehicle] [!] vehicles: {vehicles}")

        if not vehicles:
            print(f"[PlayerVehicle] [!] No vehicle identified - Seq {pk.seq}")
            return None

        if isinstance(vehicles, PlayerVehicle):
            results.append(vehicles)
            print(f"slot_joueur={vehicles.slot}, vehicle_id={vehicles.vehicle_id}, vehicle_name={vehicles.vehicle_name}")
        elif isinstance(vehicles, list):
            for vehicle in vehicles:
                results.append(vehicle)
                print(
                    f"slot_joueur={vehicle.slot}, vehicle_id={vehicle.vehicle_id}, vehicle_name={vehicle.vehicle_name}")

        return results


    except Exception as e:
        import traceback
        print(f"[PlayerVehicle] [!] Global error : {e}", file=sys.stderr)
        traceback.print_exc()  # Très utile pour voir la ligne exacte de l'erreur
        return None

def _parse_from_raw_vehicles(
        list_raw: list[bytes], vehicles_database: dict, lineup_per_players: dict) -> dict[int, PlayerVehicle]:
    """
    Extrait les données des véhicules des joueurs dans les replays.

    :param list_raw: Liste qui contient les bytes du replay
    :param vehicles_database: Dictionnaire filtrer des véhicules utilisés lors de la game
    :param lineup_per_players: dictionnaire qui donne la lineup de véhicules possible pour chaque joueur
    :return:
    """

    # On utilise directement le dictionnaire final pour éviter une liste intermédiaire
    vehicles_players_dict: dict[int, PlayerVehicle] = {}
    unknown_vehicles_players: list[str] = []

    for data in list_raw:
        header = parse_header(data)
        decompressed = _decompress_packet_stream(data, header)
        stream = io.BytesIO(decompressed)

        for pk in read_packets(stream):

            if pk.packet_type == 6:
                parsed_data = parse_v_player(pk, vehicles_database, lineup_per_players)

                # Normalisation en liste pour traiter uniformément (objet unique ou liste)
                items = parsed_data if isinstance(parsed_data, list) else [parsed_data]

                for item in items:
                    if isinstance(item, str):
                        unknown_vehicles_players.append(item)
                        continue

                    if isinstance(item, PlayerVehicle):
                        # Déduplication directe : on remplace si le slot est nouveau
                        # ou si le nom du véhicule a changé (dernière occurrence gagne)
                        existing = vehicles_players_dict.get(item.slot)
                        if existing is None or item.vehicle_name != existing.vehicle_name:
                            vehicles_players_dict[item.slot] = item

    dict_sorted = dict(sorted(vehicles_players_dict.items()))

    #print(f"DICT BEFORE CHECK          :{dict_sorted}")

    unfound_slot = _search_unfound_slot(dict_sorted)
    unknown_vehicles_players: list[str] = []

    if not unfound_slot:
        return dict_sorted

    for data in list_raw:
        header = parse_header(data)
        decompressed = _decompress_packet_stream(data, header)
        stream = io.BytesIO(decompressed)

        for pk in read_packets(stream):

            if pk.packet_type == 6:
                parsed_data = _double_check_vehicle(pk, vehicles_database, lineup_per_players, unfound_slot)

                # Normalisation en liste pour traiter uniformément (objet unique ou liste)
                items = parsed_data if isinstance(parsed_data, list) else [parsed_data]

                for item in items:
                    if isinstance(item, str):
                        unknown_vehicles_players.append(item)
                        continue

                    if isinstance(item, PlayerVehicle):
                        # Déduplication directe : on remplace si le slot est nouveau
                        # ou si le nom du véhicule a changé (dernière occurrence gagne)
                        existing = dict_sorted.get(item.slot)
                        if existing is None or item.vehicle_name != existing.vehicle_name:
                            dict_sorted[item.slot] = item



    dict_after_check = dict(sorted(dict_sorted.items()))
    #print(f"DICT AFTER CHECK            :{dict_after_check}")
    # Si un tri par slot est strictement nécessaire :
    return dict_sorted #dict_after_check

# =============================================================================
# 9. EXTRACTION DES STATS DU RESULTS BLK
# =============================================================================

@dataclass
class PlayerStats:
    """Stats de fin de partie pour un joueur, extraites du Results BLK."""
    slot:            int
    name:            str
    user_id:         int
    team:            int
    kills:           int
    deaths:          int
    assists:         int
    damage_dealt:    float
    score:           int
    activity:        float      # % d'activité (0.0–1.0)
    air_kills:       int
    ground_kills:    int
    naval_kills:     int
    vehicle:         str
    is_winner:       bool
    raw:             dict = field(default_factory=dict, repr=False)

@dataclass
class VehiclesReplays:
    vehicles: list


def extract_vehicle_map_from_results(results: dict) -> dict[int, str]:
    """
    Extrait le mapping userId → vehicle_name depuis matchingInfo du Results BLK.

    Structure du Results BLK (replays serveur récents) :
        matchingInfo
          {userId_str}
            crafts_info
              array0          ← véhicule actif (rankUnused=False)
                name          ← ex: "ussr_t_80b"
                rankUnused    ← "False" = véhicule joué
              array1..N       ← véhicules de réserve (rankUnused=True)

    Retourne {user_id: vehicle_name} pour les 16 joueurs.
    """
    vehicle_map: dict[int, str] = {}
    if not results:
        return vehicle_map

    matching = results.get('matchingInfo')
    if not isinstance(matching, dict):
        return vehicle_map

    for uid_str, info in matching.items():
        try:
            uid = int(uid_str)
        except (ValueError, TypeError):
            continue
        if not isinstance(info, dict):
            continue

        crafts = info.get('crafts_info')
        if not isinstance(crafts, dict):
            continue

        # Cherche le véhicule actif (rankUnused=False)
        vehicle = ''
        # Parcours array0, array1... dans l'ordre
        i = 0
        while True:
            key = f'array{i}'
            craft = crafts.get(key)
            if craft is None:
                break
            if isinstance(craft, dict):
                rank_unused = craft.get('rankUnused', 'True')
                if str(rank_unused).lower() == 'false':
                    vehicle = _get_str(craft, 'name', 'shortName', 'unitName')
                    break
            i += 1

        # Fallback : prend array0 si aucun n'est marqué actif
        if not vehicle:
            array0 = crafts.get('array0')
            if isinstance(array0, dict):
                vehicle = _get_str(array0, 'name', 'shortName', 'unitName')

        if uid and vehicle:
            vehicle_map[uid] = vehicle

    return vehicle_map


def extract_stats_from_results(results: dict) -> tuple[list[PlayerStats], list[str], dict]:
    """
    Extrait les statistiques de fin de partie depuis le Results BLK.

    Structure typique :
        root
          result[]
            nick / name
            team
            kills / killsAir / killsGround / killsNaval
            deaths
            assists
            damage / totalDamage
            score
            activity
            vehicles[] → name
    """
    stats = []
    vehicles_replay = []
    vehicles_by_player = {}

    if not results:
        return stats, vehicles_replay, vehicles_by_player

    result_list = (results.get('result') or results.get('results')
                   or results.get('player') or results.get('mplace') or [])

    if isinstance(result_list, dict):
        result_list = [result_list]

    print(f"RESULTS :{results}")

    # Détermine l'équipe gagnante
    winner_team = _get_int(results, 'winTeam', 'winner', 'victorTeam')
    print(f"winner :{winner_team}")

    for i, r in enumerate(result_list):
        if not isinstance(r, dict):
            continue

        print(f"R                        :{r}")
        name    = _get_str(r, 'nick', 'name', 'playerName')
        user_id = _get_int(r, 'userId', 'uid', 'userID', 'playerId')
        team    = _get_int(r, 'team', 'teamId')
        score   = _get_int(r, 'score', 'totalScore', 'points')

        print(f"NAME                     :{name}")
        print(f"USER ID                  :{user_id}")
        # Kills multitypes
        air_kills        = _get_int(r, 'kills')
        print(f"KILLS                    :{air_kills}")
        ai_kills    = _get_int(r, 'aiKills')
        print(f"AI KILLS                 :{ai_kills}")
        ground_kills = _get_int(r, 'killsGround', 'tankKills', 'groundKills')
        print(f"GROUND KILLS             :{ground_kills}")
        naval_kills  = _get_int(r, 'killsNaval',  'navalKills','shipKills')
        print(f"NAVAL KILLS              :{naval_kills}")

        kills = air_kills + ground_kills + naval_kills + ai_kills

        deaths   = _get_int(r, 'deaths', 'numDeaths', 'losses')
        assists  = _get_int(r, 'assists', 'numAssists')

        # Dégâts
        damage = 0.0
        for key in ('damage', 'totalDamage', 'damageDealt', 'damageGiven'):
            v = r.get(key)
            if v is not None:
                try:
                    damage = float(v); break
                except (TypeError, ValueError):
                    pass

        # Activité (souvent 0.0–1.0 ou 0–100)
        activity = 0.0
        raw_act = r.get('activity') or r.get('activityMult')
        if raw_act is not None:
            try:
                activity = float(raw_act)
                if activity > 1.0:
                    activity /= 100.0
            except (TypeError, ValueError):
                pass

        # Véhicule principal : d'abord depuis vehicles[], sinon depuis matchingInfo
        vehicles = r.get('vehicles') or r.get('vehicle') or r.get('aircraft') or {}
        if isinstance(vehicles, list):
            vehicles = vehicles[0] if vehicles else {}
        if not isinstance(vehicles, dict):
            vehicles = {}
        vehicle = _get_str(vehicles, 'name', 'shortName', 'unitName')

        # Fallback : matchingInfo[userId].crafts_info.array0 (rankUnused=False)
        if not vehicle and user_id:
            lineup_per_players = []
            matching = results.get('matchingInfo', {})
            info = matching.get(str(user_id), {}) if isinstance(matching, dict) else {}
            crafts = info.get('crafts_info', {}) if isinstance(info, dict) else {}
            if isinstance(crafts, dict):
                for k, craft in crafts.items():
                    if isinstance(craft, dict):
                        if craft["name"]:
                            lineup_per_players.append(craft["name"])

                            if not craft["name"] in vehicles_replay:
                                vehicles_replay.append(craft["name"])

                vehicles_by_player[i] = lineup_per_players

                j = 0
                while True:
                    craft = crafts.get(f'array{j}')
                    if craft is None: break
                    if isinstance(craft, dict): #str(craft.get('rankUnused','True')).lower() == 'false'
                        vehicle = _get_str(craft, 'name', 'shortName', 'unitName')
                        break
                    j += 1

                if not vehicle:
                    a0 = crafts.get('array0')
                    if isinstance(a0, dict):
                        vehicle = _get_str(a0, 'name', 'shortName', 'unitName')

        is_winner = (team == winner_team and winner_team != 0)

        stats.append(PlayerStats(
            slot=i, name=name, user_id=user_id, team=team,
            kills=kills, deaths=deaths,
            assists=assists, damage_dealt=damage, score=score,
            activity=activity, air_kills=air_kills,
            ground_kills=ground_kills, naval_kills=naval_kills,
            vehicle=vehicle, is_winner=is_winner, raw=r,
        ))

    return stats, vehicles_replay, vehicles_by_player


# =============================================================================
# 10. FUSION — TABLE JOUEURS COMPLÈTE
# =============================================================================

@dataclass
class Player:
    """Vue unifiée d'un joueur, toutes sources confondues."""
    slot:         int
    name:         str
    clan_tag:     str
    user_id:      int
    team:         int
    title:        str
    # Véhicule principal (settings ou déduit des kills)
    vehicle:      str       # identifiant interne (ex: germ_panther_II)
    country:      str
    rank:         int
    # Champs avec valeurs par défaut (doivent être après les champs sans défaut)
    vehicle_name: str  = ''   # nom affiché en jeu (ex: Pz.Kpfw. Panther II) via all_units
    vehicle_type: str  = ''   # code type : MT/LT/HT/TT/AA/F/BB/BA/H
    vehicle_br:   float= 0.0  # BR réaliste sol
    vehicle_image_path: str = '' # Path de l'image de chaque vehicule
    # Tous les véhicules observés en jeu (via kills en tant que killer ou victim)
    vehicles_seen:  set = field(default_factory=set, repr=False)
    # Stats fin de partie
    lineup_vehicles: list | None = None
    kills:        int  = 0
    deaths:       int  = 0
    assists:      int  = 0
    air_kills:    int  = 0
    ground_kills: int  = 0
    naval_kills:  int  = 0
    damage_dealt: float = 0.0
    score:        int  = 0
    activity:     float = 0.0
    is_winner:    bool  = False
    # Kills commis durant la partie
    kills_recorded: list = field(default_factory=list, repr=False)
    # Awards reçus
    awards:         list = field(default_factory=list, repr=False)


def build_player_table(
    settings_players:  list[PlayerFromSettings],
    slot_players:      list[PlayerFromSlot],
    stats:             list[PlayerStats],
    vehicles_players:  dict[int, PlayerVehicle],
    lineup_players:    dict[int, VehicleInfo],
    vehicle_map:       dict = None,  # userId → vehicle_name depuis matchingInfo
) -> dict[int, Player]:
    """
    Construit une table slot → Player en fusionnant les trois sources.
    Priorité : slot_players (live) > settings_players (statique) > stats (résultats)
    vehicle_map (optionnel) : userId→vehicle depuis matchingInfo du Results BLK.
    """
    table: dict[int, Player] = {}

    # Source 2 : paquets Slot
    # On crée un Player pour TOUS les slots nommés (vrais joueurs)
    # Les slots sans nom (fantômes) sont ignorés ici — ils n'ont pas de vrai joueur

    for sp in settings_players:
        table[sp.slot] = Player(
            slot=sp.slot, name=sp.name, clan_tag=sp.clan_tag,
            user_id=sp.user_id, team=sp.team, title="",
            vehicle=sp.vehicle, country=sp.country, rank=sp.rank,
        )

    print(f"slot_players={slot_players}")
    print(f"list_vehicle_players={vehicles_players}")
    print(f"len_list_slot_players={len(slot_players)} | len_list_vehicle_players={len(vehicles_players)}")

    #vehicles_dict = {v.slot: v for v in vehicles_players}

    for slp in slot_players:
        has_real_name = bool(slp.name and slp.name.strip())
        if slp.slot in table:
            p = table[slp.slot]
            if slp.name:        p.name     = slp.name
            if slp.clan_tag:    p.clan_tag = slp.clan_tag
            if slp.user_id:     p.user_id  = slp.user_id
            if slp.title:       p.title    = slp.title
        elif has_real_name:
            v = vehicles_players.get(slp.slot)
            l = lineup_players.get(slp.slot)
            if v:
                # Le véhicule existe pour ce slot précis
                table[slp.slot] = Player(
                    slot=slp.slot, name=slp.name, clan_tag=slp.clan_tag,
                    user_id=slp.user_id, team=0, title=slp.title,
                    vehicle=v.vehicle_id,
                    vehicle_name=v.vehicle_name,
                    vehicle_type=v.vehicle_type,
                    country=v.country,
                    rank=0, vehicle_image_path=v.image_path,
                    vehicle_br=v.vehicle_br,
                    lineup_vehicles=l

                )
                print(f"Tout est correct => slot={slp.slot} | vehicle={v.vehicle_id}")

            else:
                # Le véhicule est manquant pour ce slot (le cas du slot 14 dans ton exemple)
                table[slp.slot] = Player(
                    slot=slp.slot, name=slp.name, clan_tag=slp.clan_tag,
                    user_id=slp.user_id, team=0, title=slp.title,
                    vehicle="?", vehicle_name="?",
                    vehicle_type="?", country="?",
                    rank=0, vehicle_image_path="?",
                    vehicle_br=0, lineup_vehicles=l

                )
                print(f"Manque des données => slot={slp.slot} | vehicle='?'")



        # Les slots sans nom sont ignorés : pas de Player créé pour eux

    def _search_clan_tag(id_player: Player.user_id, verbose: bool = False) -> str:
        url = f"https://api.thunderinsights.dk/v1/users/direct/{id_player}"

        if verbose:
            print(f"  Récupération ThunderInsights pour ID {id_player}...")

        try:
            data = _get_json(url)

            # Vérification si data est un dictionnaire (structure attendue pour un utilisateur direct)
            # Si l'API renvoie une liste ou un dict contenant les infos du joueur :
            if isinstance(data, dict):
                # On cherche la clé "clanTag". Si elle n'existe pas, on retourne ""
                return data.get("clanTag", "")

            # Si l'API renvoie une liste d'unités (comme semble le suggérer votre code original)
            elif isinstance(data, list):
                for unit in data:
                    if unit.get("clanTag"):
                        return unit["clanTag"]
                return ""

            return ""

        except Exception as e:
            if verbose:
                print(f"  [!] Erreur ThunderInsights : {e}", file=sys.stderr)
            return ""


    # Source 3 : Results BLK (stats + vehicle si manquant)
    # Les stats ont un index 0-N qui NE correspond PAS aux vrais slots réseau.
    # Les vrais slots viennent des PlayerInit (slot_players). On match uniquement
    # par nom pour ne pas créer de faux doublons avec des slots 0-15 fantômes.
    tag_clan_1 = ""
    tag_clan_2 = ""

    for st in stats:
        matched = None
        # Priorité 1 : match par nom exact
        for p in table.values():
            if p.name and p.name == st.name:
                matched = p

                if st.team == 1:
                    if not p.clan_tag:
                        if tag_clan_1:
                            p.clan_tag = tag_clan_1
                        break
                    tag_clan_1 = p.clan_tag
                    break

                if st.team == 2:
                    if not p.clan_tag:
                        if tag_clan_2:
                            p.clan_tag = tag_clan_2
                        break
                    tag_clan_2 = p.clan_tag
                    break
                else:
                    break

        # Priorité 2 : match par user_id si disponible
        if matched is None and st.user_id:
            for p in table.values():
                if p.user_id and p.user_id == st.user_id:
                    matched = p

                    if st.team == 1:
                        if not p.clan_tag:
                            if tag_clan_1:
                                p.clan_tag = tag_clan_1
                            break
                        tag_clan_1 = p.clan_tag
                        break

                    if st.team == 2:
                        if not p.clan_tag:
                            if tag_clan_2:
                                p.clan_tag = tag_clan_2
                            break
                        tag_clan_2 = p.clan_tag
                        break
                    else:
                        break

        # Priorité 3 : si table vide (pas de PlayerInit), créer à l'index stats
        if matched is None and not table:
            matched = Player(
                slot=st.slot, name=st.name, clan_tag="", user_id=0,
                team=st.team, title="", rank=0, #vehicle=st.vehicle, country="",
            )
            table[st.slot] = matched
        # Priorité 4 : slot_fallback seulement si les slots sont dans la plage 0-15
        # (replays anciens sans PlayerInit)
        if matched is None and all(k < 16 for k in table.keys()):
            matched = table.get(st.slot)
        if matched is None:
            # Dernier recours : création avec un slot négatif pour ne pas polluer
            # les vrais slots réseau
            matched = Player(
                slot=-(st.slot + 1), name=st.name, clan_tag="", user_id=st.user_id,
                team=st.team, title="", rank=0, #vehicle=st.vehicle, country="",
            )
            table[-(st.slot + 1)] = matched

        if not matched.clan_tag:
            matched.clan_tag = _search_clan_tag(matched.user_id, verbose=True)

        matched.kills        = st.kills
        matched.deaths       = st.deaths
        matched.assists      = st.assists
        matched.air_kills    = st.air_kills
        matched.ground_kills = st.ground_kills
        matched.naval_kills  = st.naval_kills
        matched.damage_dealt = st.damage_dealt
        matched.score        = st.score
        matched.activity     = st.activity
        matched.is_winner    = st.is_winner
        if st.vehicle and not matched.vehicle:
            matched.vehicle = st.vehicle
        if st.team and not matched.team:
            matched.team = st.team

    return table


# =============================================================================
# 11. STRUCTURES DE RÉSULTAT GLOBAL
# =============================================================================

@dataclass
class ReplayData:
    header:               WRPLHeader
    settings_raw:         Optional[dict]
    results_raw:          Optional[dict]
    players:              dict            # slot → Player
    chats:                list = field(default_factory=list)
    kills:                list = field(default_factory=list)
    movements:            list = field(default_factory=list)
    awards:               list = field(default_factory=list)
    packet_count:         int  = 0
    unknown_slot_msgs:    list = field(default_factory=list)  # messages slot non-parsés


# =============================================================================
# 12. PARSE PRINCIPAL
# =============================================================================

def _decompress_packet_stream(data: bytes, header: WRPLHeader) -> bytes:
    """
    Décompresse le flux de paquets zlib depuis un fichier .wrpl brut.

    Format v2.54- : stream zlib directement à pkt_offset (commence par 78 xx)
    Format v2.55+ : préfixe de N octets avant le stream zlib
      ex: 02 01 16 04 00 1b 06 00 | 78 01 ...
                    préfixe 8B    ^-- zlib ici
    """
    pkt_offset = HEADER_SIZE + header.settings_blk_size

    def _try(raw: bytes) -> bytes:
        """Tente plusieurs variantes de décompression zlib."""
        for wb in (15, 47, -15):
            try:
                return zlib.decompress(raw, wbits=wb)
            except zlib.error:
                pass
        return b''

    # Bloc à décompresser
    if header.results_blk_offset > pkt_offset:
        block = data[pkt_offset : header.results_blk_offset]
    else:
        block = data[pkt_offset:]

    if not block:
        return b''

    # Essai 1 : format direct v2.54- (commence par 78)
    result = _try(block)
    if result:
        return result

    # Essai 2 : format v2.55+ — cherche le premier 0x78 dans les 32 premiers octets
    # et saute le préfixe (typiquement 8 octets)
    for skip in range(1, min(33, len(block))):
        if block[skip] == 0x78:
            result = _try(block[skip:])
            if result:
                return result

    return b''


def _parse_single_file(
    data: bytes,
    parse_movements: bool = False,
    verbose: bool = True,
    label: str = "",
    debug_blk: bool = False,
    dump_unknown_slots: bool = False
) -> tuple[WRPLHeader, Optional[dict], Optional[dict], list, list, list, list, list, list, int]: #vehicles_database: dict = None
    """
    Parse un seul fichier .wrpl et retourne toutes ses données brutes.
    Retourne : (header, settings_blk, results_blk,
                settings_players, slot_players, chats, kills, awards, movements, pkt_count)
    """
    header = parse_header(data)
    tag = f"[{label}] " if label else ""

    if verbose:
        srv = "Serveur" if header.is_server else "Client"
        print(f"  {tag}{srv} part={header.replay_part_number}  "
              f"settings={header.settings_blk_size}B  "
              f"results_at={header.results_blk_offset}")

    # Settings BLK
    settings_blk = None
    if header.settings_blk_size > 0:
        raw = data[HEADER_SIZE : HEADER_SIZE + header.settings_blk_size]
        try:
            settings_blk = parse_blk(raw)
        except Exception as e:
            if verbose:
                print(f"  {tag}[!] Settings BLK : {e}", file=sys.stderr)

    # Results BLK
    results_blk = None
    if header.results_blk_offset > 0:
        try:
            results_blk = parse_blk(data[header.results_blk_offset:], True)
        except Exception as e:
            if verbose:
                print(f"  {tag}[!] Results BLK : {e}", file=sys.stderr)

    settings_players = extract_players_from_settings(settings_blk or {})

    # Flux de paquets
    decompressed = _decompress_packet_stream(data, header)
    if not decompressed and verbose:
        print(f"  {tag}[!] Flux de paquets vide ou illisible", file=sys.stderr)

    stream = io.BytesIO(decompressed)
    vehicle_players, chats, kills, awards, movements, slot_players_all = [], [], [], [], [], []
    pkt_count = 0

    for pk in read_packets(stream):
        pkt_count += 1

        if pk.packet_type == 3:
            msg = parse_chat(pk)
            if msg:
                chats.append(msg)
        elif pk.packet_type == 4:
            raw_slot = parse_slot_packet(pk, _dump_unknown=dump_unknown_slots)
            # Sépare les PlayerFromSlot des messages inconnus (str) si dump activé
            for item in raw_slot:
                if isinstance(item, PlayerFromSlot):
                    #print(f"ITEM      :{item}\n")
                    slot_players_all.append(item)
                elif isinstance(item, str) and dump_unknown_slots:
                    slot_players_all.append(item)

            #print(f"PARSE KILL DATA        :{pk}")
            kill = parse_kill(pk)
            if kill:
                kills.append(kill)
            award = parse_award(pk)
            if award:
                awards.append(award)
            if parse_movements:
                mov = parse_movement(pk)
                if mov:
                    movements.append(mov)


        """elif pk.packet_type == 6:
            vehicle_player = parse_v_player(pk, vehicles_database)

            if vehicle_player:
                print(f"_parse_vehicle: {vehicle_player}")
                if isinstance(vehicle_player, PlayerVehicle):
                    vehicle_players.append(vehicle_player)
                elif isinstance(vehicle_player, list):
                    vehicle_players.extend(vehicle_player)"""

    print(f"AWARDS:   {awards}\n")

    named_slots = sorted(set(
        slp.slot for slp in slot_players_all
        if isinstance(slp, PlayerFromSlot) and slp.name and slp.name.strip()
    ))

    if verbose:
        print(f"  {tag}{pkt_count} paquets | "
              f"{len(named_slots)} slot-players nommés (slots {named_slots[:8]}{'...' if len(named_slots)>8 else ''}) | "
              f"{len(kills)} kills | {len(chats)} chats | {len(awards)} awards") # | {len(vehicle_players)} vehicles found

    return (header, settings_blk, results_blk,
            settings_players, slot_players_all,
            chats, kills, awards, movements, pkt_count) #vehicle_players



def _compute_net_offset(players: dict, kills: list) -> int:
    """
    Détermine l'offset entre les slots réseau (victim_slot dans les kills)
    et les slots logiques (index dans players{}).

    Les kills contiennent deux espaces de nommage :
    - killer_slot : slot logique (0-15), directement dans players{}
    - victim_slot : slot réseau (ex: 24-39) = slot_logique + offset

    Calcule l'offset en cherchant, pour chaque kill où le killer est connu,
    à quelle valeur constante victim_slot - X tombe dans players{}.

    Retourne 0 si aucun offset n'est trouvé (slots déjà cohérents).
    """
    if not kills or not players:
        return 0

    logical_slots = set(players.keys())
    victim_slots  = [k.victim_slot for k in kills if k.victim_slot >= 0]
    if not victim_slots:
        return 0

    # Cas simple : victim_slots déjà dans players → pas d'offset
    if any(vs in logical_slots for vs in victim_slots):
        return 0

    # Recherche de l'offset le plus fréquent parmi {victim_slot - ls}
    # pour ls dans logical_slots
    from collections import Counter
    offset_votes: Counter = Counter()

    for kill in kills:
        ks = kill.killer_slot
        vs = kill.victim_slot
        if ks < 0 or vs < 0:
            continue
        if ks in logical_slots:
            # Le killer est connu à slot ks.
            # Les victim_slots devraient aussi être dans logical_slots après offset.
            # On cherche l'offset tel que vs - offset ∈ logical_slots.
            for ls in logical_slots:
                if vs - ls >= 0:
                    offset_votes[vs - ls] += 1

    if not offset_votes:
        return 0

    # Valide l'offset le plus fréquent : tous les victim_slots doivent y atterrir
    best_offset, _ = offset_votes.most_common(1)[0]

    # Confirme que cet offset est cohérent pour TOUS les kills
    consistent = sum(
        1 for vs in victim_slots
        if (vs - best_offset) in logical_slots
    )

    # Accepte si au moins 50% des victims sont résolues
    if consistent >= len(victim_slots) * 0.5:
        return best_offset

    return 0


def parse_replay_files(paths: list[str], parse_movements: bool = False,
                       verbose: bool = True, debug_blk: bool = False,
                       dump_unknown_slots: bool = False) -> 'ReplayData':
    """
    Parse un ou plusieurs fichiers .wrpl appartenant à la même session.

    Stratégie multi-fichiers (OpenPartedReplay — wrplRead.go) :
      - Partie 0  → fournit le Header officiel + Settings BLK (liste joueurs + véhicules)
      - Parties intermédiaires → fournissent les paquets (kills, chats, slots)
      - Dernière partie → fournit le Results BLK (stats finales)
      - Toutes les parties contribuent leurs paquets, dans l'ordre part_number croissant
    """
    if not paths:
        raise ValueError("Aucun fichier fourni")

    _vdb = load_vehicle_db(verbose=False) or {}

    # Lit et trie tous les fichiers par numéro de partie
    parts: list[tuple[int, bytes, str]] = []

    for path in paths:
        raw = Path(path).read_bytes()
        try:
            hdr = parse_header(raw)
            parts.append((hdr.replay_part_number, raw, path))
        except Exception as e:
            print(f"  [!] {path} ignoré : {e}", file=sys.stderr)

    if not parts:
        raise ValueError("Aucun fichier .wrpl valide trouvé")

    parts.sort(key=lambda x: x[0])

    #print(f"PARTS SORT         :{parts.sort(key=lambda x: x[0])}") => Donne rien

    ref_header = parse_header(parts[0][1])

    #print(f"REF HEADER         :{ref_header}") => Donne qlqch

    if verbose:
        print(f"\n  Session  : {ref_header.session_hex}")
        print(f"  Map      : {ref_header.level}")
        print(f"  Type     : {ref_header.battle_type}")
        print(f"  Difficulté: {ref_header.difficulty}")
        print(f"  Fichiers : {len(parts)} partie(s)")

    # Vérifie la cohérence des sessions
    for part_num, raw, path in parts:
        h = parse_header(raw)
        if h.session_id != ref_header.session_id:
            print(f"  [!] {path} session {h.session_hex} ≠ {ref_header.session_hex}, ignoré",
                  file=sys.stderr)

    # Parse chaque partie
    all_raw:              list[bytes] = []
    all_settings_players: list[PlayerFromSettings] = []
    all_slot_players:     list[PlayerFromSlot]     = []
    all_chats:            list  = []
    all_kills:            list  = []
    all_awards:           list  = []
    all_movements:        list  = []
    all_pkt_count:        int   = 0
    all_vehicles_players:  list[PlayerVehicle]  = []
    final_settings_blk:   Optional[dict] = None
    final_results_blk:    Optional[dict] = None

    for part_num, raw, path in parts:
        fname = Path(path).name
        (hdr, settings_blk, results_blk,
         settings_players, slot_players,
         chats, kills, awards, movements, pkt_count) = _parse_single_file(
            raw, parse_movements=parse_movements, verbose=verbose,
            label=fname, debug_blk=debug_blk,
            dump_unknown_slots=dump_unknown_slots
        ) #vehiclesplayers

        if raw:
            all_raw.append(raw)

        # Settings BLK : la partie 0 fait autorité (la plus complète)
        if settings_blk and (final_settings_blk is None or part_num == 0):
            final_settings_blk = settings_blk

        # Results BLK : la dernière partie fait autorité
        if results_blk:
            final_results_blk = results_blk

        # Settings players : part 0 fait autorité, mais on enrichit si vide
        if settings_players and (not all_settings_players or part_num == 0):
            all_settings_players = settings_players

        # Sépare PlayerFromSlot des messages inconnus (str dump)
        for item in slot_players:
            if isinstance(item, PlayerFromSlot):
                all_slot_players.append(item)
            elif isinstance(item, str):
                all_slot_players.append(item)  # gardé pour affichage
        all_chats.extend(chats)
        all_kills.extend(kills)
        all_awards.extend(awards)
        all_movements.extend(movements)
        #all_vehicles_players.extend(vehiclesplayers)

        all_pkt_count += pkt_count

    print(f"RESULT BLK: {final_results_blk}")

    # Stats depuis Results BLK
    uncompleted_stats, possibles_vehicles_replay, lineup_per_player = extract_stats_from_results(final_results_blk or {})

    # Détermination de l'ensemble des véhicules observés en jeu (via kills et matchingInfo)
    _vdb_filter = _vehicles_filter(
        vehicles=_vdb,
        names_vehicles= possibles_vehicles_replay
    )

    print(f"DB FILTER            :{_vdb_filter}")

    complete_stats = _update_win_team(
        stats=uncompleted_stats,
        awards=all_awards
    )

    vehicles_players_slot = _parse_from_raw_vehicles(
        list_raw=all_raw,
        vehicles_database=_vdb_filter,
        lineup_per_players=lineup_per_player
    )

    print(f"VEHICLES SLOT PLAYERS            :{vehicles_players_slot}")
    print(f"LINEUP PER PLAYERS            :{lineup_per_player}")

    # Déduplication slot players : garde le dernier par slot
    slot_deduped: dict[int, PlayerFromSlot] = {}
    unknown_slot_msgs: list[str] = []

    #print(f"ALL SLOT PLAYERS      :{all_slot_players}\n")
    #print(f"UNKNOW SLOT PLAYERS      :{unknown_slot_msgs}\n")

    for slp in all_slot_players:
        if isinstance(slp, str):
            unknown_slot_msgs.append(slp)
            continue
        existing = slot_deduped.get(slp.slot)
        if existing is None:
            # Première fois qu'on voit ce slot → insère
            slot_deduped[slp.slot] = slp
        elif slp.name and slp.name.strip() and not (existing.name and existing.name.strip()):
            # Le nouveau a un vrai nom, l'existant non → remplace
            slot_deduped[slp.slot] = slp
        # Sinon : garde l'existant (priorité au premier nom non-vide rencontré)

    vehicles_players_deduped: dict[int, PlayerVehicle] = {}
    unknown_vehicles_players: list[str] = []

    """for vplyr in all_vehicles_players:
        #print(f"vplyr={vplyr}")
        if isinstance(vplyr, str):
            unknown_vehicles_players.append(vplyr)
            continue
        existing = vehicles_players_deduped.get(vplyr.slot)
        if existing is None or vplyr.vehicle_name != existing.vehicle_name:
            vehicles_players_deduped[vplyr.slot] = vplyr

    vehicles_players_slot = sorted({v.slot: v for v in list(vehicles_players_deduped.values())}.values(),
                                   key=lambda v: v.slot)"""

    """# On trie par la clé (le numéro de slot) et on récupère les objets
    vehicles_players_deduped = sorted({v.slot: v for v in all_vehicles_players}.values(), key=lambda v: v.slot)"""

    named_in_dedup  = sum(1 for p in slot_deduped.values() if p.name and p.name.strip())
    total_in_dedup  = len(slot_deduped)
    named_slots_all = sorted(p.slot for p in slot_deduped.values() if p.name and p.name.strip())

    print(f"  Stats    : {complete_stats}")

    if verbose:
        print(f"\n  Total paquets  : {all_pkt_count}")
        print(f"  Joueurs settings: {len(all_settings_players)}")
        print(f"  Slots PlayerInit: {total_in_dedup} total, {named_in_dedup} nommés")
        print(f"  Slots nommés    : {named_slots_all}")
        print(f"  Stats résultats : {len(complete_stats)}")
        print(f"  Kills total     : {len(all_kills)}")
        print(f"  Chats total     : {len(all_chats)}")
        print(f"  Awards total    : {len(all_awards)}")

    # Fusion des trois sources
    vehicle_map = extract_vehicle_map_from_results(final_results_blk or {})

    """print(
                f"HDR             :{hdr}\n"
                f"SET BLK         :{settings_blk}\n"
                f"RESULT BLK      :{results_blk}\n"
                f"SET PLAYERS     :{settings_players}\n"
                f"SLOT PLAYERS    :{all_slot_players}\n"
                f"CHATS           :{chats}\n"
                f"KILLS           :{kills}\n"
                f"AWARDS          :{awards}\n"
                f"MOVEMENTS       :{movements}\n"
                f"PKT COUNT       :{pkt_count}\n"
            )"""

    """print(f"STATS         :{stats}")
    print(f"VEHICLE MAP   :{vehicle_map}")"""
    players = build_player_table(
        settings_players=all_settings_players,
        slot_players=list(slot_deduped.values()),
        stats=complete_stats,
        vehicles_players=vehicles_players_slot,
        lineup_players=lineup_per_player,
        vehicle_map=vehicle_map
    )

    # ── Calcul automatique de l'offset réseau ──────────────────────────────
    # Les PlayerInit utilisent des slots logiques 0-N (index de session)
    # Les kills utilisent des slots réseau (ex: 24-39) = slots logiques + offset
    # On détermine cet offset en cherchant le killer_slot qui matche un joueur connu
    # (le killer_slot est dans la plage des slots logiques 0-15)
    # et en calculant : offset = victim_slot - killer_slot_réseau_attendu
    #
    # Méthode : le killer_slot dans les kills est DÉJÀ le slot logique (0-15)
    # car les PlayerInit sont aux slots 0-15 et players{} les contient
    # L'offset s'applique seulement aux victim_slots
    # offset = median(victim_slot) - median(slot_logique_correspondant)
    # On calcule via : pour chaque kill, killer est connu (slot 0-15),
    # victim_slot - ?  → il faut trouver l'offset
    # Heuristique robuste : offset = min(victim_slots) - 0, ou on cherche le
    # décalage tel que les victim_slots - offset tombent dans [0, nb_joueurs)

    net_offset = _compute_net_offset(players, all_kills)
    if verbose and net_offset != 0:
        print(f"  Offset réseau détecté : +{net_offset} (victim_slot - {net_offset} = slot_logique)")

    # ── Enrichissement : kills et awards → joueurs ───────────────────────
    for k in all_kills:

        # Résolution killer (slot logique direct)
        p_killer = players.get(k.killer_slot)
        if p_killer is None and k.killer_slot >= 0:
            p_killer = Player(k.killer_slot, f"slot#{k.killer_slot}", '', 0, 0, '', '', '', 0)
            players[k.killer_slot] = p_killer

        # Résolution victim : essaie d'abord avec l'offset, puis direct
        p_victim = None
        if k.victim_slot >= 0:
            victim_logical = k.victim_slot - net_offset
            p_victim = players.get(victim_logical)
            if p_victim is None:
                # Fallback : essai direct (cas où victim_slot est déjà logique)
                p_victim = players.get(k.victim_slot)

        victim_display_slot = k.victim_slot - net_offset if net_offset else k.victim_slot

        if p_killer:
            p_killer.kills_recorded.append({
                'time_ms':        k.time_ms,
                'damage_type':    k.damage_type,
                'vehicle':        k.killer_vehicle,
                'victim_slot':    victim_display_slot,
                'victim_name':    p_victim.name if p_victim else f"slot#{victim_display_slot}",
                'victim_vehicle': k.victim_vehicle,
            })
            if k.killer_vehicle:
                p_killer.vehicles_seen.add(k.killer_vehicle)
                # Priorité : vehicle du kill > matchingInfo (plus fiable = vraiment utilisé)
                if not p_killer.vehicle or p_killer.vehicle != k.killer_vehicle:
                    p_killer.vehicle = k.killer_vehicle

        if p_victim:
            if k.victim_vehicle:
                p_victim.vehicles_seen.add(k.victim_vehicle)
                if not p_victim.vehicle:
                    p_victim.vehicle = k.victim_vehicle

    for a in all_awards:
        p = players.get(a.player_slot)
        if p:
            p.awards.append({'time_ms': a.time_ms, 'name': a.award_name})

    return ReplayData(
        header=ref_header,
        settings_raw=final_settings_blk,
        results_raw=final_results_blk,
        players=players,
        chats=all_chats,
        kills=all_kills,
        movements=all_movements,
        awards=all_awards,
        packet_count=all_pkt_count,
        unknown_slot_msgs=unknown_slot_msgs,
    )


def parse_replay(path: str, parse_movements: bool = False,
                 verbose: bool = True) -> 'ReplayData':
    """
    Parse un seul fichier .wrpl.
    Pour un replay multi-parties, utiliser parse_replay_dir() ou parse_replay_files().
    """
    return parse_replay_files([path], parse_movements=parse_movements, verbose=verbose)


def parse_replay_dir(dirpath: str, parse_movements: bool = False,
                     verbose: bool = True, debug_blk: bool = False,
                     dump_unknown_slots: bool = False) -> 'ReplayData':
    """
    Parse tous les fichiers .wrpl d'un dossier (replay serveur multi-parties).
    Équivalent de loadReplayMultipartDir dans load.go.
    """
    dir_path = Path(dirpath)
    paths = sorted(dir_path.glob('*.wrpl'))
    if not paths:
        raise ValueError(f"Aucun fichier .wrpl dans {dirpath}")
    if verbose:
        print(f"Dossier : {dirpath}  ({len(paths)} fichier(s))")
    return parse_replay_files([str(p) for p in paths],
                               parse_movements=parse_movements, verbose=verbose,
                               debug_blk=debug_blk,
                               dump_unknown_slots=dump_unknown_slots)


# =============================================================================
# 13. TÉLÉCHARGEMENT DEPUIS LES SERVEURS GAIJIN (downloader.go)
# =============================================================================

BASE_URL = "https://wt-game-replays.warthunder.com"


def download_replay(session_hex: str, dest_dir: str = "fetchedReplays",
                    verbose: bool = True) -> list[str]:
    """
    Télécharge les parties d'un replay serveur depuis Gaijin.
    URL format : {BASE_URL}/{session_hex}/{partNum:04d}.wrpl
    Retourne la liste des fichiers téléchargés.
    """
    out_dir = Path(dest_dir) / session_hex
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    part = 0

    while True:
        fname    = f"{part:04d}.wrpl"
        out_path = out_dir / fname
        url      = f"{BASE_URL}/{session_hex}/{fname}"

        if out_path.exists() and out_path.stat().st_size > 0:
            if verbose:
                print(f"  [cache] {fname}")
            downloaded.append(str(out_path))
            part += 1
            continue

        if verbose:
            print(f"  GET {url} ...", end=" ", flush=True)

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'wrpl-parser/1.0'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    content = resp.read()
                    out_path.write_bytes(content)
                    if verbose:
                        print(f"OK ({len(content):,} octets)")
                    downloaded.append(str(out_path))
                    part += 1
                elif resp.status in (404, 403):
                    if verbose:
                        print(f"fin (partie {part} → {resp.status})")
                    break
                else:
                    if verbose:
                        print(f"erreur HTTP {resp.status}")
                    break
        except urllib.error.HTTPError as e:
            if e.code in (404, 403):
                if part == 0:
                    print(f"  [!] Session introuvable : {e.code}")
                else:
                    if verbose:
                        print(f"fin après {part} partie(s)")
                break
            else:
                print(f"  [!] HTTP {e}")
                break
        except Exception as e:
            print(f"  [!] {e}")
            break

    return downloaded


def parse_multipart_replay(paths: list[str], **kwargs) -> Optional[ReplayData]:
    """
    Parse un replay multi-parties (replay serveur segmenté).
    Concatène les flux de paquets dans l'ordre des parties.
    Utilise le header + settings de la partie 0, les résultats de la dernière.
    """
    if not paths:
        return None

    # Lit et trie par numéro de partie
    parts = []
    for p in paths:
        data = Path(p).read_bytes()
        try:
            hdr = parse_header(data)
            parts.append((hdr.replay_part_number, data, hdr))
        except Exception as e:
            print(f"  [!] {p} : {e}", file=sys.stderr)

    if not parts:
        return None

    parts.sort(key=lambda x: x[0])

    # Utilise wrpl_parser sur la première partie pour header+settings
    # puis concatène les streams
    return parse_replay(paths[parts[0][0]], **kwargs)


# =============================================================================
# 14. EXPORT
# =============================================================================

class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return obj.hex()
        if hasattr(obj, '__dataclass_fields__'):
            d = asdict(obj)
            # Supprime les champs 'raw' pour alléger
            d.pop('raw', None)
            return d
        return super().default(obj)


def to_json(replay: ReplayData) -> dict:
    """Sérialise toutes les données en dict JSON-compatible."""

    def player_to_dict(p: Player) -> dict:
        return {
            'slot':          p.slot,
            'name':          p.name,
            'clan_tag':      p.clan_tag,
            'user_id':       p.user_id,
            'team':          p.team,
            'title':         p.title,
            'vehicle':        p.vehicle,
            'vehicle_name':   p.vehicle_name,
            'vehicle_type':   p.vehicle_type,
            'vehicle_br':     p.vehicle_br,
            'vehicle_image_path':     p.vehicle_image_path,
            'vehicles_seen':  sorted(p.vehicles_seen),
            'country':       p.country,
            'rank':          p.rank,
            'kills':         p.kills,
            'deaths':        p.deaths,
            'assists':       p.assists,
            'air_kills':     p.air_kills,
            'ground_kills':  p.ground_kills,
            'naval_kills':   p.naval_kills,
            'damage_dealt':  p.damage_dealt,
            'score':         p.score,
            'activity':      round(p.activity, 4),
            'is_winner':     p.is_winner,
            'kills_recorded': p.kills_recorded,
            'awards':         p.awards,
        }

    # Exclure les joueurs fantômes (sans nom ou avec nom "slot#X")
    def is_real_player(p: Player) -> bool:
        return bool(p.name and not p.name.startswith('slot#'))

    team1 = sorted(
        [player_to_dict(p) for p in replay.players.values()
         if p.team == 1 and is_real_player(p)],
        key=lambda x: -x['score'])
    team2 = sorted(
        [player_to_dict(p) for p in replay.players.values()
         if p.team == 2 and is_real_player(p)],
        key=lambda x: -x['score'])
    unknown = [player_to_dict(p) for p in replay.players.values()
               if p.team not in (1, 2) and is_real_player(p)]

    return {
        'session_id':     replay.header.session_hex,
        'map':            replay.header.level,
        'battle_type':    replay.header.battle_type,
        'difficulty':     replay.header.difficulty,
        'start_time':     replay.header.start_time,
        'is_server':      replay.header.is_server,
        'version':        replay.header.version,
        'packet_count':   replay.packet_count,
        'teams': {
            'team1': team1,
            'team2': team2,
            'unknown': unknown,
        },
        'chats':     [asdict(c) for c in replay.chats],
        'kills':     [asdict(k) for k in replay.kills],
        'awards':    [asdict(a) for a in replay.awards],
        'movements': [asdict(m) for m in replay.movements],
    }


def export_csv_all(replay: ReplayData, prefix: str = "replay"):
    """Exporte players / kills / chats / awards / movements en CSV séparés."""
    import csv

    # --- players ---
    with open(f"{prefix}_players.csv", 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['slot', 'team', 'name', 'clan_tag', 'user_id', 'title',
                    'vehicle', 'vehicle_name', 'vehicle_br', 'vehicles_seen', 'country', 'rank',
                    'kills', 'deaths', 'assists', 'air_kills', 'ground_kills',
                    'naval_kills', 'damage_dealt', 'score', 'activity', 'is_winner'])
        for p in sorted(replay.players.values(), key=lambda x: (x.team, -x.score)):
            w.writerow([
                p.slot, p.team, p.name, p.clan_tag, p.user_id, p.title,
                p.vehicle, p.vehicle_name, p.vehicle_br, '|'.join(sorted(p.vehicles_seen)), p.country, p.rank,
                p.kills, p.deaths, p.assists, p.air_kills, p.ground_kills,
                p.naval_kills, round(p.damage_dealt, 1), p.score,
                round(p.activity, 4), p.is_winner,
            ])

    # --- kills ---
    with open(f"{prefix}_kills.csv", 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['seq', 'time_ms', 'time_s', 'damage_type',
                    'killer_slot', 'killer_name', 'killer_vehicle',
                    'victim_slot', 'victim_name', 'victim_vehicle'])
        _ep = Player(0,'','',0,0,'','','',0)
        net_off = _compute_net_offset(replay.players, replay.kills)
        for k in replay.kills:
            kname  = replay.players.get(k.killer_slot, _ep).name
            victim_logical = k.victim_slot - net_off if (net_off and k.victim_slot >= 0) else k.victim_slot
            vp     = replay.players.get(victim_logical) or (replay.players.get(k.victim_slot) if k.victim_slot >= 0 else None)
            vname  = (vp.name if vp and vp.name else "") if k.victim_slot >= 0 else ""
            vveh   = k.victim_vehicle or (vp.vehicle if vp else "")
            w.writerow([k.seq, k.time_ms, round(k.time_ms / 1000, 2),
                        hex(k.damage_type),
                        k.killer_slot, kname, k.killer_vehicle,
                        victim_logical if k.victim_slot >= 0 else "", vname, vveh])

    # --- chats ---
    with open(f"{prefix}_chats.csv", 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['seq', 'time_ms', 'time_s', 'channel_type', 'is_enemy',
                    'sender', 'content'])
        for c in replay.chats:
            w.writerow([c.seq, c.time_ms, round(c.time_ms / 1000, 2),
                        c.channel_type, c.is_enemy, c.sender, c.content])

    # --- awards ---
    with open(f"{prefix}_awards.csv", 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['seq', 'time_ms', 'time_s', 'player_slot', 'player_name',
                    'award_type', 'award_name'])
        for a in replay.awards:
            aname = replay.players.get(a.player_slot, Player(0,'','',0,0,'','','',0)).name
            w.writerow([a.seq, a.time_ms, round(a.time_ms / 1000, 2),
                        a.player_slot, aname, a.award_type, a.award_name])

    # --- movements ---
    if replay.movements:
        with open(f"{prefix}_movements.csv", 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['seq', 'time_ms', 'time_s', 'eid', 'x', 'y', 'z'])
            for m in replay.movements:
                w.writerow([m.seq, m.time_ms, round(m.time_ms / 1000, 2),
                             m.eid, round(m.x, 2), round(m.y, 2), round(m.z, 2)])

    print(f"CSV exportés avec préfixe '{prefix}_'")


# =============================================================================
# 15. AFFICHAGE CONSOLE
# =============================================================================

def print_summary(replay: ReplayData):
    hdr = replay.header
    print(f"\n{'='*60}")
    print(f"  {hdr.level}  |  {hdr.battle_type}")
    print(f"  Session : {hdr.session_hex}  |  v{hdr.version}")
    print(f"  {'Serveur' if hdr.is_server else 'Client'}  |  "
          f"Difficulté {hdr.difficulty}  |  Durée limite {hdr.time_limit}s")
    print(f"{'='*60}")

    teams = {1: [], 2: [], 0: []}
    for p in sorted(replay.players.values(), key=lambda x: -x.score):
        # Ignore les joueurs fantômes (slots sans nom créés lors de l'enrichissement)
        if not p.name or p.name.startswith('slot#'):
            continue
        teams[p.team if p.team in (1, 2) else 0].append(p)

    for team_id, players in [(1, teams[1]), (2, teams[2])]:
        winner_flag = "  ★ GAGNANT" if any(p.is_winner for p in players) else ""
        print(f"\n  Équipe {team_id}{winner_flag}")
        print(f"  {'Joueur':<60} {'Clan':<10} {'Véhicule':<32} {'Type':<5}"
              f"{'K':>4} {'Air kill':>12} {'Ground kill':>12} {'D':>4} {'Ass':>4} {'Dégâts':>9} {'Score':>7} {'Activ':>6}")
        print(f"  {'-'*103}")
        for p in players:
            clan = f"[{p.clan_tag}]" if p.clan_tag else ""
            if p.vehicle_name:
                #br_str = f" {p.vehicle_br}" if p.vehicle_br else ""
                disp_v = p.vehicle_name #+ br_str
            #elif p.vehicle:
                #disp_v = p.vehicle
            #elif p.vehicles_seen:
                #disp_v = sorted(p.vehicles_seen)[0]
            else:
                disp_v = "?"
            vtype  = p.vehicle_type or ""
            print(f"  {p.name:<60} {clan:<10} {disp_v:<32} {vtype:<5}"
                  f"{p.kills:>4} {p.air_kills:>12} {p.ground_kills:>12} {p.deaths:>4} {p.assists:>4} "
                  f"{p.damage_dealt:>9.0f} {p.score:>7} {p.activity*100:>5.1f}%")

    if teams[0]:
        real_unknown = [p for p in teams[0] if p.name and not p.name.startswith('slot#')]
        if real_unknown:
            print(f"\n  Équipe non déterminée ({len(real_unknown)} joueurs sans équipe dans les résultats)")
            for p in real_unknown:
                disp_v = p.vehicle or (sorted(p.vehicles_seen)[0] if p.vehicles_seen else "?")
                print(f"    {p.name:<30} {disp_v}")

    print(f"\n  Kills en jeu  : {len(replay.kills)}")
    print(f"  Messages chat : {len(replay.chats)}")
    print(f"  Awards        : {len(replay.awards)}")

    if replay.chats:
        print(f"\n  --- Chat (10 premiers) ---")
        for c in replay.chats[:10]:
            print(f"    [{c.time_ms/1000:6.1f}s] {c.sender}: {c.content}")

    if replay.kills:
        print(f"\n  --- Kills ---")
        _ep2 = Player(0,'','',0,0,'','','',0)

        #print(f"_EP2         :{_ep2}")
        net_off = _compute_net_offset(replay.players, replay.kills)
        #print(f"NET OFF         :{net_off}")
        #print(f"REPLAY KILL         :{replay.kills}")
        for k in replay.kills: #[:10]
            kname = replay.players.get(k.killer_slot, _ep2).name or f"slot#{k.killer_slot}"

            #print(f"KILL NAME          :{kname}")

            victim_logical = k.victim_slot - net_off if net_off else k.victim_slot
            vp = replay.players.get(victim_logical) or replay.players.get(k.victim_slot)
            vname = (vp.name if vp and vp.name else f"slot#{victim_logical}") if k.victim_slot >= 0 else "?"
            vveh = k.victim_vehicle or (vp.vehicle if vp else "")
            print(f"    [{k.time_ms/1000:6.1f}s] {kname} ({k.killer_vehicle}) "
                  f"→ {vname} ({vveh})  dmg=0x{k.damage_type:02x}")


# =============================================================================
# 16. BASE DE DONNÉES VÉHICULES — 2 API EXTERNES
# =============================================================================

_VEHICLE_DB_CACHE_DEFAULT = Path(__file__).parent / "all_units.json"

@dataclass
class VehicleInfo:
    """Métadonnées d'un véhicule WT issues du all_units.json (all_units.py)."""
    id:               str
    display_name:     str    # Nom affiché en jeu (ex: "Pz.Kpfw. Panther II")
    country:          str    # Nation WT (ex: "germany", "ussr", "usa"…)
    vehicle_type:     str    # Code court : MT/LT/HT/TT/AA/F/BB/BA/H
    vehicle_full_type: str   # Type long (ex: "medium_tank", "fighter"…)
    br:               float = 0.0  # BR réaliste sol
    image_path:       str = ''   # Path de l'image de chaque véhicule

    @classmethod
    def from_dict(cls, d: dict) -> 'VehicleInfo':
        """Construit depuis un dict all_units.json (clés variables selon la source)."""
        return cls(
            id               = d.get('unit_full_name') or d.get('id', ''),
            display_name     = d.get('full_name')      or d.get('display_name', ''),
            country          = d.get('country', ''),
            vehicle_type     = d.get('vehicle_type', ''),
            vehicle_full_type= d.get('vehicle_full_type') or d.get('vehicle_full_type', ''),
            br               = float(d.get('realistic_ground_br') or d.get('br') or 0),
            image_path       = d.get('image_path')
        )


# Mapping préfixe ID → nation WT
_COUNTRY_PREFIXES: list[tuple[str, str]] = [
    ('germ_', 'germany'), ('ussr_', 'ussr'),   ('us_',  'usa'),
    ('uk_',   'britain'), ('fr_',   'france'),  ('it_',  'italy'),
    ('jp_',   'japan'),   ('cn_',   'china'),   ('sw_',  'sweden'),
    ('il_',   'israel'),
]

# Mots-clés dans l'ID indiquant un avion (heuristique)
_AIR_ID_HINTS = frozenset([
    'bf_109', 'fw_190', 'he_', 'ju_', 'do_', 'me_', 'ta_',
    'mig_', 'yak_', 'il_2', 'il_10', 'pe_', 'su_', 'tu_', 'la_',
    'spitfire', 'hurricane', 'mosquito', 'lancaster', 'wellington',
    'p_51', 'p_47', 'p_38', 'p_40', 'p_39', 'p_61', 'b_17', 'b_29',
    'f4u', 'f6f', 'f4f', 'tbf', 'sbd', 'dauntless',
    'a6m', 'ki_', 'b5n', 'd3a', 'j2m', 'n1k',
    'sm_79', 'g_55', 'mc_', 'cr_',
    'saab_', 'j21', 'j22',
    'mirage', 'mystere', 'ouragan', 'vautour',
])


def _country_from_id(vid: str) -> str:
    for prefix, country in _COUNTRY_PREFIXES:
        if vid.startswith(prefix):
            return country
    return ''


def _type_from_id(vid: str) -> str:
    vl = vid.lower()
    if any(hint in vl for hint in _AIR_ID_HINTS):
        return 'aircraft'
    if any(k in vl for k in ('ship', 'destroyer', 'cruiser', 'frigate', 'battleship')):
        return 'ship'
    return 'tank'


def _fetch_url(url: str, timeout: int = 20) -> Optional[bytes]:
    """HTTP GET simple, retourne None si échec."""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'wrpl-parser/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _parse_units_csv(data: bytes) -> dict[str, str]:
    """
    Parse lang/units.csv du datamine.

    Le fichier a typiquement deux formats selon la version du datamine :
      Format A (TSV) :  vehicle_id<TAB>display_name[<TAB>...]
      Format B (CSV) :  "vehicle_id","display_name"[,...]

    Retourne {vehicle_id: display_name}.
    Ne conserve que les IDs qui ressemblent à des véhicules (pas les missions, cartes…).
    """
    result: dict[str, str] = {}
    try:
        text = data.decode('utf-8', errors='replace')
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(';') or line.startswith('#'):
                continue
            # Détecte le séparateur
            if '\t' in line:
                parts = line.split('\t', 2)
            else:
                parts = line.split(',', 2)
            if len(parts) < 2:
                continue
            vid   = parts[0].strip().strip('"').strip("'")
            vname = parts[1].strip().strip('"').strip("'")
            # Filtre : ID doit ressembler à un nom de véhicule WT
            # (commence par un préfixe nation ou contient '_')
            if not vid or not vname or vid == 'ID' or vid == 'id':
                continue
            if len(vid) < 3 or len(vname) < 2:
                continue
            result[vid] = vname
    except Exception:
        pass
    return result


def load_vehicle_db(force_refresh: bool = False,
                    verbose: bool = True) -> dict[str, 'VehicleInfo']:
    """
    Charge la base de données véhicules depuis vehicle_db.json (cache local).

    Le cache doit être généré UNE FOIS avec build_vehicle_db.py :
        python build_vehicle_db.py

    Avec force_refresh=True, retélécharge depuis le datamine GitHub
    (nécessite une connexion internet).

    Retourne dict {vehicle_id: VehicleInfo}.
    """
    cache = _VEHICLE_DB_CACHE_DEFAULT

    if not cache.exists():
        print("[Load database vehicles] - CACHE INEXISTANT")
    else:
        print("[Load database vehicles] - CACHE EXISTANT")

    # ── 1. Cache local (chemin par défaut ou explicite) ───────────────────
    if not force_refresh and cache.exists():
        try:
            with open(cache, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            db = {}
            for k, v in raw.items():
                try:
                    db[k] = VehicleInfo.from_dict(v)
                except Exception:
                    pass
            if verbose:
                print(f"  Base véhicules       : {len(db):,} véhicules ← {cache.name}")
            return db
        except Exception as e:
            if verbose:
                print(f"  [!] Cache corrompu ({cache.name}) : {e} → retéléchargement")

    # ── 2. Cache absent → guide l'utilisateur ────────────────────────────
    if not force_refresh and not cache.exists():
        if verbose:
            print(f"  [!] Cache véhicules introuvable : {cache}")
            print(f"  [!] Lance d'abord : python build_vehicle_db.py")
            print(f"  [!] Puis relance  : python wrpl_parser.py <replay> --enrich")
        return {}

    """
    # ── 3. Téléchargement depuis le datamine (--refresh-db) ──────────────
    if verbose:
        print(f"  Téléchargement lang/units.csv depuis le datamine GitHub...")

    csv_bytes = _fetch_url(_UNITS_CSV_URL)
    if not csv_bytes:
        if verbose:
            print("  [!] Téléchargement échoué.")
            print("  [!] Lance build_vehicle_db.py sur un PC avec accès internet,")
            print("  [!] puis copie vehicle_db.json ici.")
        return {}

    names = _parse_units_csv(csv_bytes)
    if not names:
        if verbose:
            print("  [!] Aucun véhicule parsé depuis lang/units.csv")
        return {}

    # Construit les VehicleInfo
    db: dict[str, VehicleInfo] = {}
    for vid, vname in names.items():
        db[vid] = VehicleInfo(
            id=vid,
            display_name=vname,
            country=_country_from_id(vid),
            vehicle_type=_type_from_id(vid),
        )

    if verbose:
        print(f"  Base véhicules chargée : {len(db):,} véhicules")"""

    # ── 4. Sauvegarde du cache ────────────────────────────────────────────
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with open(cache, 'w', encoding='utf-8') as f:
            json.dump({k: vars(v) for k, v in db.items()},
                      f, ensure_ascii=False, separators=(',', ':'))
        if verbose:
            print(f"  Cache sauvegardé     : {cache}")
    except Exception as e:
        if verbose:
            print(f"  [!] Cache non sauvegardé : {e}", file=sys.stderr)

    return db


def enrich_vehicles_from_db(players: dict, vehicle_db: dict[str, VehicleInfo],
                             verbose: bool = False) -> int:
    """
    Enrichit les Player avec les métadonnées de la base véhicules :
    - vehicle_name : nom affiché en jeu (ex: "Pz.V Panther")
    - country      : nation si pas encore définie (ex: "germany")

    Retourne le nombre de joueurs dont vehicle_name a été rempli.
    """
    enriched = 0
    for p in players.values():
        # Si pas de véhicule principal mais vehicles_seen → prend le premier connu
        if not p.vehicle and p.vehicles_seen:
            # Préfère un véhicule présent dans le db
            for vs in sorted(p.vehicles_seen):
                if vs in vehicle_db:
                    p.vehicle = vs
                    break
            if not p.vehicle:
                p.vehicle = sorted(p.vehicles_seen)[0]

        if not p.vehicle:
            continue

        info = vehicle_db.get(p.vehicle)
        if info:
            p.vehicle_name = info.display_name
            p.vehicle_type = info.vehicle_type
            p.vehicle_br   = info.br
            p.vehicle_image_path  = info.image_path
            if not p.country and info.country:
                p.country = info.country
            enriched += 1
        elif verbose:
            pass  # vehicle_id inconnu dans le db (véhicule très récent ou non véhiculé)

    return enriched


# =============================================================================
# 17. CLI
# =============================================================================

# =============================================================================
# ONLINE — Récupération véhicules depuis thunder.nanachi.party
# =============================================================================

def build_display_full_name_index(vehicle_db) -> dict:
    """
    Construit {display_name_normalisé → vehicle_name, display_anme, vehicle_type, image_path, country} depuis all_units.json.
    Priorité : match exact sur full_name, puis variantes normalisées.
    Accepte un dict de dicts (all_units.json brut) ou de VehicleInfo.
    """
    import re as _re

    idx: dict[str, str] = {}

    def _add(key: str, vinfo: tuple):
        k = key.lower().strip()
        if k and k not in idx:
            idx[k] = vinfo

    for vid, entry in vehicle_db.items():
        try:
            # On tente l'accès "Style Objet" (prioritaire)
            # On utilise getattr pour gérer le cas où l'attribut est None tout en restant concis
            full = (getattr(entry, 'display_name', '') or '').strip()

            vinfo = (
                vid,
                (entry.display_name or '').strip(),
                (entry.country or '').strip(),
                (entry.vehicle_type or '').strip(),
                (entry.image_path or '').strip()
            )

        except AttributeError:
            # Si l'accès par point échoue, on bascule sur le "Style Dictionnaire"
            print(f"INFO: Passage en mode dictionnaire pour {vid}")

            full = (entry.get('full_name') or entry.get('display_name') or '').strip()
            vinfo = (
                vid,
                (entry.get("full_name") or entry.get('display_name') or '').strip(),
                (entry.get("country") or '').strip(),
                (entry.get("vehicle_type") or '').strip(),
                (entry.get("image_path") or '').strip()
            )
        except Exception as e:
            print(f"Erreur inattendue sur {vid}: {e}")
            continue

        # Index 1 : exact (priorité max)
        _add(full, vinfo)

        # Index 2 : sans caractères spéciaux
        clean = _re.sub(r"[()'▀▄]", ' ', full)
        clean = _re.sub(r'\s+', ' ', clean).strip()
        _add(clean, vinfo)

        """# Index 3 : mots finaux (2 et 3 derniers)
        words = clean.split()
        if len(words) >= 2: _add(' '.join(words[-2:]), vid)
        if len(words) >= 3: _add(' '.join(words[-3:]), vid)"""

    # Corrections manuelles fréquentes warthunder.com / nanachi
    _FIXES = {
        'strf 9040c': 'sw_strf_90c',   'strf 9040b': 'sw_strf_90b',
        'a2d-1': 'a2d',
        'type 60 sprg (c)': 'jp_type_60_sprg_c',
        'centurion mk.5/1': 'uk_centurion_mk_5_raac',
        'centurion mk 3':   'uk_centurion_mk3',
        'elc bis':          'fr_amx_elc_bis',
        'somua sm':         'fr_somua_sm',
        'pzh 2000':         'germ_pzh_2000',
        'object 268':       'ussr_object_268',
        'is-4m': 'ussr_is_4m',   'is-3': 'ussr_is_3',
        'is-2 (1944)': 'ussr_is_2_1944',
        'marder a1-': 'germ_marder_a1',
        'tiger ii': 'germ_pzkpfw_vi_ausf_b_tiger_iip',
        'tiger ii (nr.1-50)': 'germ_pzkpfw_vi_ausf_b_tiger_iih',
        'lekpz m41': 'germ_m41',
        'fw 190 f-8': 'germ_fw-190f-8',
        'kugelblitz': 'germ_flakpanzer_V_Coelian',
        "sho't kal alef": 'il_centurion_shot_kal_alef',
        'm-51': 'il_m51',
        'caernarvon': 'uk_caernarvon',   'fv4202': 'uk_fv4202',
        'zsu-23-4m2': 'ussr_zsu_23_4m2',
        'm41d': 'cn_m41d',   'wz305': 'cn_wz_305',
    }
    for k, v in _FIXES.items():
        idx[k.lower()] = v

    return idx

def build_display_name_index(vehicle_db) -> dict:
    """
    Construit {vehicle_name → vehicle_id, vehicle_name, country, vehicle_type, image_path} depuis all_units.json.
    Priorité : match exact sur full_name, puis variantes normalisées.
    Accepte un dict de dicts (all_units.json brut) ou de VehicleInfo.
    """
    import re as _re

    idx: dict[str, str] = {}

    def _add(key: str, vinfo: tuple):
        k = key.lower().strip()
        if k and k not in idx:
            idx[k] = vinfo

    for vid, entry in vehicle_db.items():
        try:
            # On tente l'accès "Style Objet" (prioritaire)
            # On utilise getattr pour gérer le cas où l'attribut est None tout en restant concis
            full = (getattr(entry, 'id', '') or '').strip()

            vinfo = (
                vid,
                (entry.display_name or '').strip(),
                (entry.country or '').strip(),
                (entry.vehicle_type or '').strip(),
                (entry.image_path or '').strip()
            )

        except AttributeError:
            # Si l'accès par point échoue, on bascule sur le "Style Dictionnaire"
            print(f"INFO: Passage en mode dictionnaire pour {vid}")

            full = (entry.get('id') or entry.get('unit_full_name') or '').strip()
            vinfo = (
                vid,
                (entry.get("full_name") or entry.get('display_name') or '').strip(),
                (entry.get("country") or '').strip(),
                (entry.get("vehicle_type") or '').strip(),
                (entry.get("image_path") or '').strip()
            )
        except Exception as e:
            print(f"Erreur inattendue sur {vid}: {e}")
            continue

        # Index 1 : exact (priorité max)
        _add(full, vinfo)

        # Index 2 : sans caractères spéciaux
        clean = _re.sub(r"[()'▀▄]", ' ', full)
        clean = _re.sub(r'\s+', ' ', clean).strip()
        _add(clean, vinfo)

        """# Index 3 : mots finaux (2 et 3 derniers)
        words = clean.split()
        if len(words) >= 2: _add(' '.join(words[-2:]), vid)
        if len(words) >= 3: _add(' '.join(words[-3:]), vid)"""

    #print(f"DICT    :{idx}\n")

    return idx


def fetch_session_vehicles(
    session_id: int,
    vehicle_db: dict = None,
    verbose: bool = False,
) -> dict:
    """
    Récupère les véhicules joués depuis thunder.nanachi.party/sessions/{session_id}.

    Retourne {userId: [vehicle_id_spawn1, vehicle_id_spawn2, ...]}
    Premier élément = véhicule joué en premier spawn.

    Le display_name retourné par nanachi (ex: "Challenger DS") est résolu vers
    le vehicle_id interne (ex: "uk_challenger_1_mk_3_gulf") via all_units.json
    en prioritisant le match exact sur full_name.
    """
    import re as _re
    import html as _html

    url = f"https://thunder.nanachi.party/sessions/{session_id}"

    page = _fetch_page(url, verbose=verbose)
    if not page:
        return {}

    dn_idx = build_display_full_name_index(vehicle_db or {})
    dnid_idx = build_display_name_index(vehicle_db or {})

    def _resolve(display: str) -> str:
        display = _html.unescape(display).strip()
        key = display.lower()
        vid = dn_idx.get(key)

        prefixes_to_clean = ['tankmodels',
                             'planemodels',
                             'shipmodels',
                             'boatmodels',
                             'bombermodels']

        if not vid:
            import re as _r
            clean = _r.sub(r"[()'▀▄]", ' ', key)
            clean = _r.sub(r'\s+', ' ', clean).strip()
            vid = dn_idx.get(clean)
            if not vid and any(p in key for p in prefixes_to_clean):
                key = key.split('/')[-1]
                vid = dnid_idx.get(key)

        if not vid and verbose:
            print(f"  [online] Vehicule non résolu : {display!r}\n", file=sys.stderr)
            if any(p in key for p in prefixes_to_clean):
                print(f"  [online] Vehicule non résolu : En attente de résolution\n", file=sys.stderr)
                key = key.split('/')[-1]
                vid = dnid_idx.get(key)

                print(f"  [online] Vehicule résolu\n", file=sys.stderr) if vid else (
                    print(f"  [online] Vehicule non résolu {display!r}\n", file=sys.stderr))

        return vid or ''

    """def _parse_spawns(td_html: str) -> list:
        text = _re.sub(r'<[^>]+>', '', td_html)

        text = _html.unescape(text).strip()
        for s in text.split(',') if s.strip()
            txt = _resolve(s.strip())

        return [_resolve(s.strip()) for s in text.split(',') if s.strip()]"""

    def _parse_spawns(td_html: str) -> str:
        text = _re.sub(r'<[^>]+>', '', td_html)
        text = _html.unescape(text).strip()

        # On split et on prend le premier
        parts = [s.strip() for s in text.split(',') if s.strip()]

        return _resolve(parts[0]) if parts else ""

    result: dict = {}

    # Team 1 — col-left : spawns | clan | name+userId
    for row in _re.finditer(
            r'<tr>\s*<td class="col-left">(.*?)</td>'         
            r'\s*<td class="col-left">.*?/clans/([^"]+)"'     
            r'.*?href="/players/(\d+)"',
        page, _re.DOTALL
    ):
        spawns, tclan, uid = _parse_spawns(row.group(1)), row.group(2), int(row.group(3))
        if uid and spawns:
            result[uid] = spawns, tclan

    # Team 2 — col-right : name+userId | clan | spawns
    for row in _re.finditer(
            r'<tr>\s*<td class="col-right">.*?href="/players/(\d+)"'  
            r'.*?href="/clans/([^"]+)"' 
            r'.*?<td class="col-right">([^<]+)</td>',
        page, _re.DOTALL
    ):
        spawns, tclan, uid = _parse_spawns(row.group(3)), row.group(2), int(row.group(1))

        if uid and spawns:
            result[uid] = spawns, tclan

    if verbose:
        print(f"  [online] {len(result)} joueurs depuis thunder.nanachi.party")
    return result


def extract_vehicle_map_from_results(results: dict) -> dict:
    """
    Extrait userId → vehicle_id depuis matchingInfo du Results BLK.
    Utilise crafts_info.array0 (rankUnused=False = véhicule actif du lineup).
    """
    vehicle_map: dict = {}
    if not results:
        return vehicle_map

    matching = results.get('matchingInfo')
    if not isinstance(matching, dict):
        return vehicle_map

    for uid_str, info in matching.items():
        try:
            uid = int(uid_str)
        except (ValueError, TypeError):
            continue
        if not isinstance(info, dict):
            continue
        crafts = info.get('crafts_info')
        if not isinstance(crafts, dict):
            continue

        vehicle = ''
        i = 0
        while True:
            craft = crafts.get(f'array{i}')
            if craft is None:
                break
            if isinstance(craft, dict):
                if str(craft.get('rankUnused', 'True')).lower() == 'false':
                    vehicle = _get_str(craft, 'name', 'shortName', 'unitName')
                    break
            i += 1

        if not vehicle:
            a0 = crafts.get('array0')
            if isinstance(a0, dict):
                vehicle = _get_str(a0, 'name', 'shortName', 'unitName')

        if uid and vehicle:
            vehicle_map[uid] = vehicle

    return vehicle_map


def main():
    ap = argparse.ArgumentParser(
        description="Parseur de replays War Thunder (.wrpl) — fichier unique ou dossier multi-parties",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  # Fichier unique (replay client ou partie 0)
  python wrpl_parser.py replay.wrpl

  # Dossier multi-parties (replay serveur : 0000.wrpl, 0001.wrpl, ...)
  python wrpl_parser.py fetchedReplays/001122334455aabb/

  # Plusieurs fichiers explicites
  python wrpl_parser.py 0000.wrpl 0001.wrpl 0003.wrpl

  # Télécharge depuis Gaijin et parse directement
  python wrpl_parser.py --download 001122334455aabb

  # Export
  python wrpl_parser.py replay/ --json out.json
  python wrpl_parser.py replay/ --csv --prefix ma_partie

  # Debug : voir la structure exacte des BLK (indispensable pour diagnostiquer les véhicules)
  python wrpl_parser.py replay/ --debug-blk
        """
    )
    ap.add_argument('replay',    nargs='*', help="Fichier(s) .wrpl ou dossier contenant des .wrpl")
    ap.add_argument('--json',    metavar='FILE',   help="Export JSON complet")
    ap.add_argument('--csv',     action='store_true', help="Export CSV (plusieurs fichiers)")
    ap.add_argument('--prefix',  default='replay',    help="Préfixe des fichiers CSV (défaut: replay)")
    ap.add_argument('--movements', action='store_true', help="Inclure les mouvements (volumineux)")
    ap.add_argument('--download', metavar='SESSION_HEX',
                    help="Télécharge le replay serveur depuis Gaijin puis le parse")
    ap.add_argument('--debug-blk', action='store_true',
                    help="Affiche la structure complète des BLK (Settings + Results) pour diagnostic")
    ap.add_argument('--dump-slots', action='store_true',
                    help="Dump tous les messages slot non-reconnus (pour identifier le spawn event)")
    ap.add_argument('--scan-mpi', action='store_true',
                    help="Scanne et affiche toutes les signatures MPI type 4 inconnues (rétro-ingénierie spawn)")
    ap.add_argument('--quiet',      action='store_true', help="Moins de verbosité")
    ap.add_argument('--enrich',     action='store_true',
                    help="Enrichit les véhicules avec les noms depuis gszabi99/War-Thunder-Datamine (réseau requis)")
    ap.add_argument('--refresh-db', action='store_true', dest='refresh_db',
                    help="Force le rechargement de la base véhicules (ignore le cache)")
    ap.add_argument('--db-cache',   metavar='FILE', default=None,
                    help="Chemin du cache JSON véhicules (défaut: vehicle_db.json)")
    ap.add_argument('--online',     action='store_true',
                    help="Récupère les véhicules réels depuis thunder.nanachi.party")
    args = ap.parse_args()

    verbose = not args.quiet

    # --- Téléchargement ---
    if args.download:
        print(f"Téléchargement session {args.download} ...")
        paths = download_replay(args.download, verbose=verbose)
        if not paths:
            print("Aucun fichier téléchargé.", file=sys.stderr)
            sys.exit(1)
        print(f"Téléchargé {len(paths)} partie(s).")
        if not args.replay:
            # Auto-parse le dossier téléchargé
            args.replay = [str(Path("fetchedReplays") / args.download)]

    if not args.replay:
        ap.print_help()
        sys.exit(1)

    # --- Résolution des chemins ---
    # Accepte : dossier, fichier unique, ou liste de fichiers
    file_paths: list[str] = []
    for entry in args.replay:
        p = Path(entry)
        if p.is_dir():
            found = sorted(p.glob('*.wrpl'))
            if not found:
                print(f"[!] Aucun .wrpl dans {entry}", file=sys.stderr)
                sys.exit(1)
            file_paths.extend(str(f) for f in found)
        elif p.is_file():
            file_paths.append(str(p))
        else:
            print(f"[!] Chemin introuvable : {entry}", file=sys.stderr)
            sys.exit(1)

    if not file_paths:
        print("[!] Aucun fichier .wrpl trouvé.", file=sys.stderr)
        sys.exit(1)

    if verbose:
        print(f"Fichiers à parser ({len(file_paths)}) :")
        for f in file_paths:
            print(f"  {f}")

    # --- Scan MPI (rétro-ingénierie, exécuté avant le parse normal) ---
    if getattr(args, 'scan_mpi', False):
        print(f"\n{'='*60}")
        print("SCAN MPI — signatures type 4 inconnues :")
        print(f"{'='*60}")
        mpi_results = scan_mpi_signatures(file_paths)
        print_mpi_scan(mpi_results)
        print(f"{'='*60}\n")

    # --- Parse ---
    replay = parse_replay_files(
        file_paths,
        parse_movements=bool(args.movements),
        verbose=verbose,
        debug_blk=getattr(args, 'debug_blk', False),
    )

    # --- Debug BLK ---
    if args.debug_blk:
        print("\n" + "="*60)
        print("DEBUG Settings BLK :")
        print("="*60)
        if replay.settings_raw:
            debug_blk_structure(replay.settings_raw)
        else:
            print("  (aucun Settings BLK disponible)")
        print("\n" + "="*60)
        print("DEBUG Results BLK :")
        print("="*60)
        if replay.results_raw:
            debug_blk_structure(replay.results_raw)
        else:
            print("  (aucun Results BLK disponible)")

    # --- Dump messages slot inconnus (pour analyser le spawn event) ---
    if getattr(args, 'dump_slots', False):
        print("\n" + "="*60)
        print("DUMP messages slot inconnus (pour analyse spawn event) :")
        print("Format: UNKNOWN slot=X t=Tms hdr=XXXXXXXXXX body=...")
        print("="*60)
        # Re-parse avec dump activé pour collecter les messages
        replay2 = parse_replay_files(
            file_paths,
            parse_movements=False,
            verbose=False,
            dump_unknown_slots=True,
        )
        # Extraire les messages inconnus accumulés dans all_slot_players
        # (ils ne sont pas stockés dans ReplayData, on les affiche ici)
        if replay.unknown_slot_msgs:
            # Regrouper par header pour voir les patterns
            from collections import Counter
            header_counts = Counter()
            for msg in replay.unknown_slot_msgs:
                parts = msg.split()
                hdr = next((p for p in parts if p.startswith("hdr=")), "hdr=?")
                header_counts[hdr] += 1
            print(f"\n{len(replay.unknown_slot_msgs)} messages inconnus, {len(header_counts)} headers distincts :")
            for hdr, count in sorted(header_counts.items(), key=lambda x: -x[1])[:20]:
                print(f"  {hdr}  ({count}x)")
            print("\nExemples (5 premiers par header) :")
            shown = {}
            for msg in replay.unknown_slot_msgs:
                parts = msg.split()
                hdr = next((p for p in parts if p.startswith("hdr=")), "?")
                if shown.get(hdr, 0) < 5:
                    print(f"  {msg}")
                    shown[hdr] = shown.get(hdr, 0) + 1
        else:
            print("  Aucun message slot inconnu trouvé.")
            print("  Relancez avec --dump-slots pour activer la collecte.")

    # --- Enrichissement véhicules depuis le datamine (optionnel) ---
    if args.enrich or args.refresh_db:
        #db_cache = Path(args.db_cache) if args.db_cache else None
        vehicle_db = load_vehicle_db(
            force_refresh=args.refresh_db,
            verbose=verbose,
        )
        if vehicle_db:
            n = enrich_vehicles_from_db(replay.players, vehicle_db, verbose=verbose)
            if verbose:
                print(f"  Véhicules enrichis   : {n}/{len(replay.players)} joueurs")
        # else : load_vehicle_db a déjà affiché le message d'aide

    # --- Véhicules online depuis thunder.nanachi.party (--online) ---
    if getattr(args, 'online', False):
        session_id = replay.header.session_id
        if session_id:
            if verbose:
                print(f'  Récupération thunder.nanachi.party (session {session_id})...')
            _vdb = load_vehicle_db(verbose=False) or {}
            online = fetch_session_vehicles(session_id, vehicle_db=_vdb, verbose=verbose)
            if online:
                v_res, vn_res, c_res, vt_res, iv_res, cv_res = 0, 0, 0, 0, 0, 0
                #print(f"ONLINE    :{online}\n")
                #print(f"PLAYERS REPLAY BEFORE    :{replay.players.values()}\n")
                for p in replay.players.values():
                    if p.user_id and p.user_id in online:
                        it = iter(online[p.user_id])
                        first = next(it, '')
                        second = next(it, '')
                        #first = next((v for v in online[p.user_id] if v), '')

                        if first[0] != p.vehicle:
                            if not first[0]:
                                continue
                            p.vehicle = first[0]
                            v_res += 1

                        if first[1] != p.vehicle_name:
                            if not first[1]:
                                continue
                            p.vehicle_name = first[1]
                            vn_res += 1

                        if first[2] != p.country:
                            if not first[2]:
                                continue
                            p.country = first[2]
                            cv_res += 1

                        if first[3] != p.vehicle_type:
                            if not first[3]:
                                continue
                            p.vehicle_type = first[3]
                            vt_res += 1

                        if first[4] != p.vehicle_image_path:
                            if not first[4]:
                                continue
                            p.vehicle_image_path = first[4]
                            iv_res += 1

                        if second != p.clan_tag:
                            if not second:
                                continue

                            p.clan_tag = second
                            c_res += 1

                #print(f"PLAYERS REPLAY AFTER    :{replay.players.values()}\n")

                if verbose:
                    print(f'  Véhicules id online    : {v_res} corrigés')
                    print(f'  Nom de véhicules entier online    : {vn_res} corrigés')
                    print(f'  Type de véhicules online    : {vt_res} corrigés')
                    print(f'  Image de Véhicules online    : {iv_res} corrigés')
                    print(f'  Pays de Véhicules online    : {cv_res} corrigés')
                    print(f'  Clans online        : {c_res} corrigés\n')

    # --- Affichage résumé ---
    print_summary(replay)

    # --- Export JSON ---
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(to_json(replay), f, ensure_ascii=False, indent=2, cls=_Encoder)
        print(f"\nJSON écrit : {args.json}")

    # --- Export CSV ---
    if args.csv:
        export_csv_all(replay, prefix=args.prefix)


if __name__ == '__main__':
    main()
