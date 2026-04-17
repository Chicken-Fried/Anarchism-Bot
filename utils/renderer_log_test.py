import io
import random
import re
from pathlib import Path  # Correction typo : pathlib
from typing import Optional, List, Tuple, Dict
from wrpl.models.wrpl_config import Player, ReplayData, WRPLHeader
from wrpl.wrpl_parser import parse_replay_files

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# ── Configuration Globale ──────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
IMAGE_DIR = str(ROOT_DIR / "images" / "maps")

STAT_X_OFFSETS = [-45, -20, 0, 20, 45]
STAT_LABELS = ["AK", "GK", "D", "A", "S"]

# Couleurs pour les nouvelles statistiques
STAT_COLORS = [
    (80, 255, 130),  # AK (Air Kills) - Vert
    (60, 120, 200),  # GK (Ground Kills) - Bleu
    (255, 80, 80),  # D (Deaths) - Rouge
    (130, 180, 25),  # A (Assists) - Cyan
    (255, 220, 50),  # S (Score) - Jaune
]

# ── Dimensions et Layout ────────────────────────────────────────────────────
CANVAS_W, CANVAS_H = 940, 528
SCOREBOARD_W = 760
SCOREBOARD_H = 460
SB_X = (CANVAS_W - SCOREBOARD_W) // 2
SB_Y = (CANVAS_H - SCOREBOARD_H) // 2

GLASS_BLUR_RADIUS = 40
GLASS_OPACITY = 180
GLASS_CORNER_RADIUS = 12

HEADER_H = 75
CONTENT_Y = HEADER_H
MAX_ROWS = 8

BADGE_SIZE = 32
PLAYER_ROW_H = 48

# ── Polices ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
FONT_DIR = SCRIPT_DIR / "fonts"


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / ("JosefinSans-Bold.ttf" if bold else "JosefinSans-Regular.ttf")  # Ajuster selon tes noms réels
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _load_cn_font(size: int) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / "RuiZiRuiXianQiaoPiJian1-0-1.ttf"
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return _load_font(size, bold=False)


# ── Utilitaires ────────────────────────────────────────────────────────────

def get_full_paths_in_dir(directory_path: str) -> List[str]:
    path = Path(directory_path)
    if not path.exists() or not path.is_dir():
        return []
    return [str(f) for f in path.iterdir() if f.is_file()]


def is_chinese(text: str) -> bool:
    for char in text:
        cp = ord(char)
        if 0x4E00 <= cp <= 0x9FFF or 0x3040 <= cp <= 0x30FF or 0xAC00 <= cp <= 0xD7AF:
            return True
    return False


def _map_key(level: str) -> str:
    s = level.replace("levels/avg_", "").replace(".bin", "").strip()
    s = re.sub(
        r"_(dom|cap|conq|conq\d|conquest|domination|sector|operation|battle|assault|invasion|push|Dom|Cap|Conq)\w*$",
        "", s, flags=re.IGNORECASE)
    s = re.sub(r"_\d+$", "", s)
    return s.lower().strip("_")

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

def _create_glass_panel(w: int, h: int, corner_radius: int = 20) -> Image.Image:
    """Crée un masque pour panneau glassmorphism avec bords arrondis."""
    mask = Image.new("L", (w, h), 0)
    mask_draw = ImageDraw.Draw(mask)

    if hasattr(ImageDraw, 'rounded_rectangle'):
        mask_draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], corner_radius, fill=255)
    else:
        _draw_rounded_rect(mask_draw, [(0, 0), (w - 1, h - 1)], corner_radius, fill=255)

    return mask

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
    bg = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - CANVAS_W) // 2
    top = (new_h - CANVAS_H) // 2
    bg = bg.crop((left, top, left + CANVAS_W, top + CANVAS_H))

    enhancer = ImageEnhance.Brightness(bg.convert("RGB"))
    bg = enhancer.enhance(0.45).convert("RGBA")
    return bg

# ── Rendu des colonnes ─────────────────────────────────────────────────────

def _draw_team_column(canvas: Image.Image,
                      draw: ImageDraw.ImageDraw,
                      players_list: List,
                      y_start: int,
                      is_left_team: bool,
                      font_ltn: ImageFont.FreeTypeFont,
                      font_asia: ImageFont.FreeTypeFont,
                      font_small: ImageFont.FreeTypeFont,
                      mid_x: int) -> None:
    # L'ancrage reste le même
    TEAM_BLOCK_ANCHOR = mid_x - 70 if is_left_team else mid_x + 70

    # --- CORRECTION : On n'inverse JAMAIS les offsets ici ---
    # On utilise toujours l'ordre standard [-45, -20, 0, 20, 45]
    current_offsets = STAT_X_OFFSETS
    current_colors = STAT_COLORS if is_left_team else list(reversed(STAT_COLORS))

    for i, player in enumerate(players_list[:MAX_ROWS]):
        y_base = y_start + i * PLAYER_ROW_H
        y_center = y_base + (PLAYER_ROW_H // 2)

        # --- 1. Badge Véhicule (Inchangé) ---
        x_badge = 20 if is_left_team else SCOREBOARD_W - 52
        try:
            if player.vehicle_image_path and Path(player.vehicle_image_path).exists():
                v_img = Image.open(player.vehicle_image_path).convert("RGBA")
                v_img = v_img.resize((BADGE_SIZE, BADGE_SIZE), Image.Resampling.LANCZOS)
                canvas.paste(v_img, (x_badge, y_base + 4), v_img)
            else:
                draw.rounded_rectangle([x_badge, y_base + 4, x_badge + 32, y_base + 36], radius=6, fill=(100, 100, 100))
        except Exception:
            draw.rounded_rectangle([x_badge, y_base + 4, x_badge + 32, y_base + 36], radius=6, fill=(100, 100, 100))

        # --- 2. Stats (Chiffres) ---
        # On prépare les valeurs brutes [AK, GK, D, A, S]
        stats_vals = [player.air_kills, player.ground_kills, player.deaths, player.assists, player.score]

        # Si Team 2, on inverse les valeurs pour que le Score soit le premier (index 0)
        # Ainsi, il recevra l'offset -45 (le plus proche du centre)
        if not is_left_team:
            stats_vals = list(reversed(stats_vals))

        for val, color, offset in zip(stats_vals, current_colors, current_offsets):
            txt = str(val)
            tw = draw.textbbox((0, 0), txt, font=font_small)[2]
            draw.text((TEAM_BLOCK_ANCHOR + offset - tw // 2, y_center - 8), txt, font=font_small, fill=color)
        # --- 3. Noms et Véhicules (Inchangé) ---
        name = player.name.strip()
        vname = player.vehicle_name
        f_p = font_asia if is_chinese(name) else font_ltn
        if is_left_team:
            draw.text((x_badge + 40, y_base + 3), name, font=f_p, fill=(255, 255, 255))  # Correction typo couleur
            draw.text((x_badge + 40, y_base + 20), vname, font=font_small, fill=(200, 200, 200))
        else:
            tw_name = draw.textbbox((0, 0), name, font=f_p)[2]
            tw_vname = draw.textbbox((0, 0), vname, font=font_small)[2]
            x_end = x_badge - tw_name - 5
            draw.text((x_end, y_base + 3), name, font=f_p, fill=(255, 255, 255))
            draw.text((x_end - (tw_vname - tw_name), y_base + 20), vname, font=font_small, fill=(200, 200, 200))


# ... (Fonctions _create_glass_panel, _load_background, etc. restent identiques) ...
# [Note: Assure-toi que _load_background et les autres utilitaires sont présents comme dans ton script]

def render_scoreboard(replay_data: 'ReplayData', maps_dir: str) -> bytes:
    maps_path = Path(maps_dir)
    header = replay_data.header
    players_dict = replay_data.players

    # 1. Groupement par équipe
    teams_players: Dict[int, List] = {}
    for p in players_dict.values():
        teams_players.setdefault(p.team, []).append(p)

    team_ids = list(teams_players.keys())[:2]
    if len(team_ids) < 2: team_ids = [team_ids[0], 0] if len(team_ids) == 1 else [0, 1]

    team1_list = teams_players.get(team_ids[0], [])
    team2_list = teams_players.get(team_ids[1], [])

    score1 = sum(p.score for p in team1_list)
    score2 = sum(p.score for p in team2_list)
    winner_id = team_ids[0] if score1 > score2 else team_ids[1]

    # 2. Fond et Canvas
    bg = _load_background(header.level, maps_path)
    canvas = bg.copy()
    mid_x = SCOREBOARD_W // 2

    # 3. Panneau Glassmorphism
    glass_region = canvas.crop((SB_X, SB_Y, SB_X + SCOREBOARD_W, SB_Y + SCOREBOARD_H))
    blurred = glass_region.filter(ImageFilter.GaussianBlur(GLASS_BLUR_RADIUS))
    glass_panel = Image.new("RGBA", (SCOREBOARD_W, SCOREBOARD_H), (35, 35, 55, GLASS_OPACITY))
    mask = _create_glass_panel(SCOREBOARD_W, SCOREBOARD_H, GLASS_CORNER_RADIUS)
    glass_final = Image.composite(blurred, glass_panel, mask)

    draw = ImageDraw.Draw(glass_final)
    f_clan = _load_font(24, True);
    f_map = _load_font(36, True)
    f_small = _load_font(13, False);
    f_ltn_p = _load_font(15, False);
    f_asia_p = _load_cn_font(15)

    # 4. Header (Clans & Map)
    clan1_name = (team1_list[0].clan_tag if team1_list else "TEAM 1").upper()
    clan2_name = (team2_list[0].clan_tag if team2_list else "TEAM 2").upper()
    c1_color = (80, 255, 130) if team_ids[0] == winner_id else (255, 80, 80)
    c2_color = (80, 255, 130) if team_ids[1] == winner_id else (255, 80, 80)

    map_disp = _map_key(header.level).replace("_", " ").title()
    map_bbox = draw.textbbox((0, 0), map_disp, font=f_map)
    draw.text((mid_x - (map_bbox[2] - map_bbox[0]) // 2, 12), map_disp, fill=(255, 255, 255, 230), font=f_map)

    draw.text((GLASS_CORNER_RADIUS + 4, 8), clan1_name, font=f_clan, fill=c1_color)
    clan2_bbox = draw.textbbox((0, 0), clan2_name, font=f_clan)
    draw.text((SCOREBOARD_W - GLASS_CORNER_RADIUS - 4 - (clan2_bbox[2] - clan2_bbox[0]), 8), clan2_name, font=f_clan,
              fill=c2_color)

    # --- NOUVEAU : Sous le Clan, afficher les types de véhicules (F/B/T/A) ---
    def get_vehicle_types_str(players: List) -> str:
        counts = {}
        for p in players:
            t = p.vehicle_type.upper()
            if t: counts[t] = counts.get(t, 0) + 1

        # On veut l'ordre : T, B, F, A puis le reste
        order = ["T", "B", "F", "A"]
        parts = []
        for t in order:
            if t in counts: parts.append(f"{counts[t]}{t}")
        for t, count in counts.items():
            if t not in order: parts.append(f"{count}{t}")
        return " / ".join(parts)

    types1 = get_vehicle_types_str(team1_list)
    types2 = get_vehicle_types_str(team2_list)
    draw.text((GLASS_CORNER_RADIUS + 4, 35), types1, font=f_small, fill=(160, 160, 160))
    draw.text((SCOREBOARD_W - GLASS_CORNER_RADIUS - 4 - draw.textbbox((0, 0), types2, f_small)[2], 35), types2,
              font=f_small, fill=(160, 160, 160))

    # 5. Labels Stats (EFFET MIROIR SYNCHRONISÉ)
    label_y = CONTENT_Y - 18
    anchor_left = mid_x - 70
    anchor_right = mid_x + 70

    # --- TEAM 1 (Gauche) : AK -> S (S'éloigne du centre vers la gauche) ---
    for label, color, offset in zip(STAT_LABELS, STAT_COLORS, STAT_X_OFFSETS):
        tw = draw.textbbox((0, 0), label, font=f_small)[2]
        draw.text((anchor_left + offset - tw // 2, label_y), label, font=f_small, fill=color)

    # --- TEAM 2 (Droite) : S -> AK (S'éloigne du centre vers la droite) ---
    # On inverse les labels et couleurs pour que le premier soit 'S',
    # MAIS on garde les offsets standards pour qu'il soit poussé vers le centre.
    rev_labels = list(reversed(STAT_LABELS))  # [S, A, D, GK, AK]
    rev_colors = list(reversed(STAT_COLORS))  # [Jaune, Cyan, Rouge, Bleu, Vert]
    # On utilise STAT_X_OFFSETS (sans reversed !)
    rev_offsets = STAT_X_OFFSETS

    for label, color, offset in zip(rev_labels, rev_colors, rev_offsets):
        tw = draw.textbbox((0, 0), label, font=f_small)[2]
        draw.text((anchor_right + offset - tw // 2, label_y), label, font=f_small, fill=color)

    # 6. Corps des joueurs (L'appel reste le même, la logique est maintenant DANS la fonction)
    _draw_team_column(canvas, draw, team1_list, CONTENT_Y, True, f_ltn_p, f_asia_p, f_small, mid_x)
    _draw_team_column(canvas, draw, team2_list, CONTENT_Y, False, f_ltn_p, f_asia_p, f_small, mid_x)

    # 7. Assemblage final
    canvas.paste(glass_final, (SB_X, SB_Y), mask)

    output = io.BytesIO()
    canvas.convert("RGB").save(output, "JPEG", quality=100, optimize=True)
    output.seek(0)
    return output.read()


# ── Test standalone ───────────────────────────────────────────────────────
if __name__ == "__main__":

    import os
    from dotenv import load_dotenv
    load_dotenv()

    ENV_DB_REPLAYS_PATH = os.getenv("DATABASE_REPLAYS_WRPL", "data/replays")
    REPLAYS_DIR = os.path.abspath(ENV_DB_REPLAYS_PATH)

    dest = f"{REPLAYS_DIR}/66e4bc200187434"
    paths = get_full_paths_in_dir(dest)
    replay_data = parse_replay_files(paths)
    print(replay_data)

    data = render_scoreboard(replay_data, maps_dir=IMAGE_DIR)

    out_path = Path("utils/scoreboard_test_1.jpg")
    out_path.write_bytes(data)
    print(f"Image générée : {out_path} ({len(data) // 1024} KB)")