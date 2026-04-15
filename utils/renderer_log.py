"""
utils/renderer_log.py — Génération d'images scoreboard pour la commande /logs.

Produit une image 940x528 par game avec effet glassmorphism iOS.
  - Fond : image de map depuis images/maps/{map_name}_{N}.jpg
  - Header : clan1 | types véhicules | MAP NAME | types | clan2
  - Colonnes : équipe1 (gauche) | K/D/Ass (centre) | équipe2 (droite)
  - Badge coloré par type de véhicule pour chaque joueur
  - Fallback sur default_{N}.jpg si map introuvable

USAGE CORRIGÉ v3.0:
    - Stats K/D/A alignées verticalement au centre de chaque ligne joueur
    - Badges ne débordent plus du panneau glassmorphism
    - Noms tronqués proprement avec "..."
"""

import io
import random
import re
import os
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from dotenv import load_dotenv
load_dotenv()

# ── Chemins et Configuration Globale ──────────────────────────────────────
BASE_DIR = Path(__file__).parent
DB_IMAGES_MAPS = os.getenv("DATABASE_IMAGES_MAPS")

IMAGE_DIR = os.path.abspath(DB_IMAGES_MAPS)

# ── Types de Véhicules (SQB) ───────────────────────────────────────────────
TYPE_COLORS: Dict[str, Tuple[int, int, int]] = {
    "T": (60, 120, 200),  # Main Battle Tank - Bleu
    "L": (80, 180, 100),  # Light Tank - Vert
    "AA": (180, 60, 60),  # Anti-Aircraft - Rouge
    "H": (90, 140, 180),  # Helicopter - Bleu ciel
    "B": (40,  200, 255),  # Bomber - Bleu cyan
    "F": (255, 220, 50),  # Aircraft - Jaune
    "?": (160, 160, 160),  # Inconnu - Gris clair
}

TYPE_ORDER = ["MT", "LT", "AA", "HT", "TT", "SPG", "FV", "HELI", "PLANE", "SUB", "SHIP"]

# ── Polices ───────────────────────────────────────────────────────────────
_FONT_PATHS_BOLD = [
    str(BASE_DIR / "fonts" / "JosefinSans-Bold.ttf")
]

_FONT_PATHS_REG = [p.replace("Bold", "").replace("-Bold", "") for p in _FONT_PATHS_BOLD] + [
    str(BASE_DIR / "fonts" / "JosefinSans-Regular.ttf")
]

_FONT_PATHS_CN = [
    str(BASE_DIR / "fonts" / "RuiZiRuiXianQiaoPiJian1-0-1.ttf")
]

# ── Dimensions Canvas et Scoreboard (CORRIGÉ) ─────────────────────────────
CANVAS_W, CANVAS_H = 940, 528  # Taille du canvas final (inchangée)
SCOREBOARD_W = 760  # Scoreboard réduit pour éviter débordement
SCOREBOARD_H = 460  # Hauteur réduite

# Position centrée avec marges de sécurité
SB_X = (CANVAS_W - SCOREBOARD_W) // 2
SB_Y = (CANVAS_H - SCOREBOARD_H) // 2

# ── Effet Glassmorphism iOS ───────────────────────────────────────────────
GLASS_BLUR_RADIUS = 40  # Flou gaussien pour l'effet verre
GLASS_OPACITY = 180  # Transparence (0-255) sur alpha - PLUS TRANSPARENT
GLASS_BORDER_WIDTH = 2  # Bordure subtile
GLASS_CORNER_RADIUS = 12  # Bords arrondis

# ── Dimensions Internes du Scoreboard (CORRIGÉ) ───────────────────────────
HEADER_H = 75  # Hauteur header
CONTENT_Y = HEADER_H  # Début contenu joueurs
MAX_ROWS = 8  # max 8 joueurs par équipe

# ── Configuration des Colonnes Joueurs (CORRIGÉ) ──────────────────────────
COL_PADDING = 24  # Padding horizontal de chaque colonne
STATS_ZONE_W = 85  # Largeur zone stats (K/D/A) - RÉDUITE
BADGE_SIZE = 32  # Taille carrée du badge véhicule - RÉDUITE
PLAYER_ROW_H = 48  # Hauteur par ligne joueur

# ── Espacement Inter-Éléments (CORRIGÉ) ───────────────────────────────────
BADGE_TEXT_PAD = 3  # Padding texte dans le badge
NAME_VEHICLE_GAP = 12  # Espace entre nom et véhicule
STATS_COL_GAP = 6  # Espace entre K, D, A - RÉDUIT

# ── Stats K/D/A (CENTRÉES SYMÉTRIQUEMENT) ───────────────────────────────
STAT_W = 24  # Largeur allouée par stat
GAP = 6      # Espace entre stats (déjà défini dans Citation 1: STATS_COL_GAP)


# ── Fonctions Utilitaires ─────────────────────────────────────────────────
def is_chinese(text: str) -> bool:
    """Détecte si la chaîne contient des caractères CJK (Chinois/Japonais/Coréen)."""
    for char in text:
        cp = ord(char)
        if 0x4E00 <= cp <= 0x9FFF or 0x3040 <= cp <= 0x30FF or 0xAC00 <= cp <= 0xD7AF:
            return True
    return False


def truncate_text(text: str, max_len: int) -> str:
    """Tronque le texte proprement avec "..." si trop long."""
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    paths = _FONT_PATHS_BOLD if bold else _FONT_PATHS_REG
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception as e:
                print(f"Erreur chargement {p}: {e}")
                continue
    try:
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()


def _load_cn_font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_PATHS_CN:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception as e:
                print(f"Erreur chargement {p}: {e}")
                continue
    return _load_font(size, bold=False)


def _create_glass_panel(w: int, h: int, corner_radius: int = 20) -> Image.Image:
    """Crée un masque pour panneau glassmorphism avec bords arrondis."""
    mask = Image.new("L", (w, h), 0)
    mask_draw = ImageDraw.Draw(mask)

    if hasattr(ImageDraw, 'rounded_rectangle'):
        mask_draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], corner_radius, fill=255)
    else:
        _draw_rounded_rect(mask_draw, [(0, 0), (w - 1, h - 1)], corner_radius, fill=255)

    return mask


def _get_text_width(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> int:
    """Retourne la largeur du texte."""
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _draw_team_column(draw: ImageDraw.ImageDraw,
                      team: list[dict],
                      y_start: int,
                      is_left_team: bool,
                      font_ltn_player: ImageFont.FreeTypeFont,
                      font_asia_player: ImageFont.FreeTypeFont,
                      font_small: ImageFont.FreeTypeFont) -> None:
    mid_x = SCOREBOARD_W // 2
    # Écartement entre les deux blocs de stats (Gauche | Droite)
    OFFSET_SIDE = -65 if is_left_team else 65
    GAP = 28  # Écart entre K, D et A

    for i, player in enumerate(team[:10]):
        y_base = y_start + i * PLAYER_ROW_H
        y_center = y_base + (PLAYER_ROW_H // 2)

        # --- Données ---
        name = str(player.get("name") or "???")
        vname = (player.get("vehicle_name") or "???")
        vt = str(player.get("vehicle_type") or "??")
        k, d, a = player.get("kills", 0), player.get("deaths", 0), player.get("assists", 0)

        # --- Stats (Côte à côte au centre) ---
        stat_x_base = mid_x + OFFSET_SIDE
        for val, off, color in [(k, -GAP, (80, 255, 130)), (d, 0, (255, 80, 80)), (a, GAP, (130, 180, 255))]:
            txt = str(val)
            tw = _get_text_width(txt, draw, font_ltn_player)
            draw.text((stat_x_base + off - tw // 2, y_center - 10), txt, font=font_ltn_player, fill=color)

        # --- Badges (Aux extrémités) ---
        x_badge = 20 if is_left_team else SCOREBOARD_W - 52
        tc = TYPE_COLORS.get(vt, (160, 160, 160))
        draw.rounded_rectangle([x_badge, y_base + 4, x_badge + 32, y_base + 36], radius=6, fill=(*tc, 220))
        draw.text((x_badge + (32 - _get_text_width(vt, draw, font_small)) // 2, y_center - 9), vt, font=font_small,
                  fill=(0, 0, 0))

        # --- Noms et Véhicules ---
        if is_left_team:
            if is_chinese(name):
                draw.text((x_badge + 42, y_base + 3), name, font=font_asia_player, fill=(255, 255, 255))
                draw.text((x_badge + 42, y_base + 20), vname, font=font_small, fill=(*tc, 200))
            else:
                draw.text((x_badge + 42, y_base + 3), name, font=font_ltn_player, fill=(255, 255, 255))
                draw.text((x_badge + 42, y_base + 20), vname, font=font_small, fill=(*tc, 200))
        else:
            x_end = x_badge - 10
            if is_chinese(name):
                draw.text((x_end - _get_text_width(name, draw, font_asia_player), y_base + 3), name,
                          font=font_asia_player, fill=(255, 255, 255))
                draw.text((x_end - _get_text_width(vname, draw, font_small), y_base + 20), vname, font=font_small,
                          fill=(*tc, 200))
            else:
                draw.text((x_end - _get_text_width(name, draw, font_ltn_player), y_base + 3), name,
                          font=font_ltn_player, fill=(255, 255, 255))
                draw.text((x_end - _get_text_width(vname, draw, font_small), y_base + 20), vname, font=font_small,
                          fill=(*tc, 200))


def _draw_rounded_rect(draw: ImageDraw.ImageDraw,
                       bbox: tuple, radius: int, fill: int):
    """Dessine un rectangle aux coins arrondis (compatibilité Pillow < 10)."""
    if len(bbox) == 2 and isinstance(bbox[0], tuple):
        x0, y0 = bbox[0]
        x1, y1 = bbox[1]
    elif len(bbox) >= 4:
        x0, y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
    else:
        raise ValueError(f"bbox invalide: {bbox}")

    draw.rectangle([x0, y0, x1, y1], fill=fill)

    corners = [
        (([x0 + radius, y0, x0 + 2 * radius, y0 + 2 * radius], 180, 270)),
        (([x1 - 3 * radius, y0, x1 - radius, y0 + 2 * radius], 270, 360)),
        (([x0 + radius, y1 - 3 * radius, x0 + 2 * radius, y1 - radius], 90, 180)),
        (([x1 - 3 * radius, y1 - 3 * radius, x1 - radius, y1 - radius], 0, 90)),
    ]

    for corner_bbox, start_angle, end_angle in corners:
        draw.arc(corner_bbox, start_angle, end_angle, fill=fill)


# ── Helpers Map ───────────────────────────────────────────────────────────

def _map_key(level: str) -> str:
    """Extrait le nom de base de la map depuis le champ level du header."""
    s = level
    s = s.replace("levels/avg_", "").replace(".bin", "").strip()
    s = re.sub(r"_(dom|cap|conq|conq\d|conquest|domination|sector|operation|"
               r"battle|assault|invasion|push|Dom|Cap|Conq)\w*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"_\d+$", "", s)
    return s.lower().strip("_")


def _find_map_image(map_name: str, maps_dir: Path) -> Optional[Path]:
    """Trouve une image de map en choisissant aléatoirement parmi les variantes."""
    candidates = []
    for n in range(3):
        p = maps_dir / f"{map_name}_{n}.jpg"
        if p.is_file():
            candidates.append(p)
    return random.choice(candidates) if candidates else None


def _load_background(level: str, maps_dir: Path) -> Image.Image:
    """Charge l'image de fond pour la map donnée."""
    map_name = _map_key(level)
    path = _find_map_image(map_name, maps_dir)

    if path is None:
        path = _find_map_image("default", maps_dir)

    if path is None:
        bg = Image.new("RGBA", (CANVAS_W, CANVAS_H), (10, 10, 20, 255))
        return bg

    bg = Image.open(path).convert("RGBA")
    bg_w, bg_h = bg.size
    scale = max(CANVAS_W / bg_w, CANVAS_H / bg_h)
    new_w, new_h = int(bg_w * scale), int(bg_h * scale)
    bg = bg.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - CANVAS_W) // 2
    top = (new_h - CANVAS_H) // 2
    bg = bg.crop((left, top, left + CANVAS_W, top + CANVAS_H))

    enhancer = ImageEnhance.Brightness(bg.convert("RGB"))
    bg = enhancer.enhance(0.45).convert("RGBA")
    return bg


def _count_types(players: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in players:
        t = (p.get("vehicle_type") or "?").upper()
        counts[t] = counts.get(t, 0) + 1
    return counts


def _format_types(counts: dict[str, int]) -> str:
    parts = []
    for t in TYPE_ORDER:
        if t in counts:
            parts.append(f"{counts[t]}{t}")
    for t, n in counts.items():
        if t not in TYPE_ORDER:
            parts.append(f"{n}{t}")
    return " / ".join(parts)


def _center_x(text: str, draw: ImageDraw.ImageDraw,
              font: ImageFont.FreeTypeFont, x1: int, x2: int) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    tw = bb[2] - bb[0]
    return x1 + (x2 - x1 - tw) // 2


def _right_x(text: str, draw: ImageDraw.ImageDraw,
             font: ImageFont.FreeTypeFont, x_right: int) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return x_right - (bb[2] - bb[0])


# ── Renderer principal (CORRIGÉ v3.0) ───────────────────────────────────

def render_scoreboard(session: dict, maps_dir: str) -> bytes:
    """Génère l'image scoreboard avec effet glassmorphism iOS."""

    maps_path = Path(maps_dir)

    # ── Fond : Image de map complète ─────────────────────────────────────
    bg = _load_background(session.get("map", ""), maps_path)
    canvas = bg.copy()

    # Réduire la luminosité du fond pour contraste
    enhancer = ImageEnhance.Brightness(bg.convert("RGB"))
    dark_bg = enhancer.enhance(0.35).convert("RGBA")

    # ── Créer le panneau glassmorphism centré ────────────────────────────
    glass_region = canvas.crop((SB_X, SB_Y, SB_X + SCOREBOARD_W,
                                SB_Y + SCOREBOARD_H))

    blurred = glass_region.copy()
    if GLASS_BLUR_RADIUS > 0:
        blurred = blurred.filter(ImageFilter.GaussianBlur(GLASS_BLUR_RADIUS))

    glass_panel = Image.new("RGBA", (SCOREBOARD_W, SCOREBOARD_H),
                            (35, 35, 55, GLASS_OPACITY))

    mask = _create_glass_panel(SCOREBOARD_W, SCOREBOARD_H, GLASS_CORNER_RADIUS)
    glass_final = Image.composite(blurred, glass_panel, mask)

    # ── Dessiner le contenu du scoreboard sur le panneau glass ───────────
    sb_draw = ImageDraw.Draw(glass_final)

    f_clan = _load_font(24, bold=True)
    f_map = _load_font(36, bold=True)
    f_types = _load_font(10, bold=False)
    f_ltn_players = _load_font(15, bold=False)
    f_asia_players = _load_cn_font(15)
    f_reg = _load_font(13, bold=False)

    # ── Header du scoreboard ─────────────────────────────────────────────
    winner = session.get("winner", 0)
    clan1 = (session.get("clan1") or "TEAM 1").upper()
    clan2 = (session.get("clan2") or "TEAM 2").upper()
    team1 = session.get("team1", [])[:MAX_ROWS]
    team2 = session.get("team2", [])[:MAX_ROWS]

    WIN_COLOR = (80, 255, 130)
    LOSE_COLOR = (255, 80, 80)

    c1_color = (WIN_COLOR if winner == 1 else LOSE_COLOR if winner == 2 else (100, 180, 255))
    c2_color = (WIN_COLOR if winner == 2 else LOSE_COLOR if winner == 1 else (255, 130, 100))

    # Clan 1 (gauche)
    sb_draw.text((GLASS_CORNER_RADIUS + 4, 8), clan1, font=f_clan, fill=c1_color)
    types1_str = _format_types(_count_types(team1))
    sb_draw.text((GLASS_CORNER_RADIUS + 4, 30), types1_str, font=f_types, fill=(160, 160, 160))

    # Nom de la map (Plus haut)
    raw_map = session.get("map", "")
    map_disp = _map_key(raw_map).replace("_", " ").title()
    mx = _center_x(map_disp, sb_draw, f_map, 0, SCOREBOARD_W)
    sb_draw.text((mx, 12), map_disp, fill=(255, 255, 255, 230), font=f_map)

    # Clan 2 (droite)
    sb_draw.text((_right_x(clan2, sb_draw, f_clan, SCOREBOARD_W - GLASS_CORNER_RADIUS - 4), 8),
                 clan2, font=f_clan, fill=c2_color)
    types2_str = _format_types(_count_types(team2))
    sb_draw.text((_right_x(types2_str, sb_draw, f_types, SCOREBOARD_W - GLASS_CORNER_RADIUS - 4), 30),
                 types2_str, font=f_types, fill=(160, 160, 160))

    # --- Ajout des en-têtes K D A au dessus des colonnes ---
    mid_x = SCOREBOARD_W // 2
    label_y = CONTENT_Y - 18
    for side_offset in [-65, 65]:
        base_x = mid_x + side_offset
        for label, off, col in [("K", -28, (80, 255, 130)), ("D", 0, (255, 80, 80)), ("A", 28, (130, 180, 255))]:
            tw = _get_text_width(label, sb_draw, f_reg)
            sb_draw.text((base_x + off - tw // 2, label_y), label, font=f_reg, fill=col)

    # ── Colonnes des joueurs (CORRIGÉ v3.0) ───────────────────────────────
    col_width = SCOREBOARD_W - HEADER_H - GLASS_CORNER_RADIUS * 4

    # Équipe 1 (gauche) : Badge → Nom/Véhicule ← Stats K/D/A
    _draw_team_column(sb_draw, team1, CONTENT_Y,
                      is_left_team=True, font_ltn_player=f_ltn_players, font_asia_player=f_asia_players, font_small=f_reg)

    # Équipe 2 (droite) : Stats K/D/A → Nom/Véhicule ← Badge
    _draw_team_column(sb_draw, team2,
                      CONTENT_Y, is_left_team=False, font_ltn_player=f_ltn_players, font_asia_player=f_asia_players, font_small=f_reg)

    # ── Assembler le panneau glass sur le canvas ─────────────────────────
    canvas.paste(glass_final, (SB_X, SB_Y), mask)

    # ── Export JPEG ───────────────────────────────────────────────────────
    output = io.BytesIO()
    canvas.convert("RGB").save(output, "JPEG", quality=100, optimize=True)
    output.seek(0)
    return output.read()


# ── Test standalone ───────────────────────────────────────────────────────
if __name__ == "__main__":
    test_session = {
        "map": "levels/avg_poland.bin",
        "clan1": "PYTON",
        "clan2": "xTHCx",
        "winner": 2,
        "team1": [
            {"name": "XxaRZze", "vehicle_name": "T-72M2 Moderna", "vehicle_type": "MT", "kills": 0, "deaths": 2,
             "assists": 0},
            {"name": "Alessandroiurlar", "vehicle_name": "Ariete (P)", "vehicle_type": "MT", "kills": 0, "deaths": 1,
             "assists": 1},
            {"name": "Renamed_Panda", "vehicle_name": "2S6", "vehicle_type": "AA", "kills": 1, "deaths": 0,
             "assists": 1},
            {"name": "Bloccose", "vehicle_name": "M1 KVT", "vehicle_type": "MT", "kills": 0, "deaths": 1, "assists": 1},
            {"name": "ILikeDaddySugar", "vehicle_name": "2S38", "vehicle_type": "LT", "kills": 0, "deaths": 0,
             "assists": 0},
            {"name": "DOMINIQUES", "vehicle_name": "T-80B", "vehicle_type": "MT", "kills": 0, "deaths": 1,
             "assists": 1},
            {"name": "TEARS_OF_FEARS", "vehicle_name": "Leopard 2A4", "vehicle_type": "MT", "kills": 0, "deaths": 3,
             "assists": 0},
            {"name": "French_Tiger", "vehicle_name": "T-80B", "vehicle_type": "MT", "kills": 0, "deaths": 0,
             "assists": 1},
        ],
        "team2": [
            {"name": "ロサリート", "vehicle_name": "Strv 121", "vehicle_type": "MT", "kills": 1, "deaths": 1,
             "assists": 0},
            {"name": "俄联邦轮椅体系享受者", "vehicle_name": "T-80B", "vehicle_type": "MT", "kills": 1, "deaths": 0,
             "assists": 0},
            {"name": "UltimateKamikazE", "vehicle_name": "2S6", "vehicle_type": "AA", "kills": 1, "deaths": 0,
             "assists": 0},
            {"name": "HighCaliber420", "vehicle_name": "Christian II", "vehicle_type": "MT", "kills": 1, "deaths": 0,
             "assists": 0},
            {"name": "Solace_ZA", "vehicle_name": "T-80B", "vehicle_type": "MT", "kills": 1, "deaths": 0, "assists": 0},
            {"name": "QUADRAXIz", "vehicle_name": "T-80B", "vehicle_type": "MT", "kills": 1, "deaths": 3, "assists": 0},
            {"name": "Rugsss", "vehicle_name": "2S38", "vehicle_type": "LT", "kills": 1, "deaths": 1, "assists": 0},
            {"name": "youssef_18", "vehicle_name": "Christian II", "vehicle_type": "MT", "kills": 1, "deaths": 0,
             "assists": 0},
        ],
    }

    data = render_scoreboard(test_session, maps_dir=IMAGE_DIR)

    out_path = Path("scoreboard_test.jpg")
    out_path.write_bytes(data)
    print(f"Image générée : {out_path} ({len(data) // 1024} KB)")
