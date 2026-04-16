"""
all_units.py — Construit all_units.json depuis deux APIs War Thunder.

Sources :
  1. https://www.wtvehiclesapi.sgambe.serv00.net  (données véhicules complètes avec BR)
  2. https://api.thunderinsights.dk/v1/units/     (noms complets + types)

Les deux sources sont fusionnées : on garde les véhicules présents dans les DEUX.
Les bateaux/navires sont exclus (pas présents dans les replays ground/air).

Améliorations vs version originale :
  - Inclut maintenant les véhicules premium, pack et squadron (couvre ju-288c, bi, a7m2…)
  - Fallback : véhicules présents dans une seule source sont quand même conservés
  - Rapport de couverture affiché en fin de script
  - Gestion propre des erreurs réseau
  - Téléchargement automatique des images PNG dans images/vehicles/[identifier].png
  - Clé image_path dans chaque entrée du dict pointant vers l'image locale

Usage :
    python all_units.py
    python all_units.py --output custom.json
    python all_units.py --no-fallback   # strict : intersection des deux sources seulement
    python all_units.py --no-images     # désactive le téléchargement des images
"""

import argparse
import json
import sys
import re
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────

WT_API_BASE = "https://wtvehiclesapi.duckdns.org/api/vehicles"
TI_API_URL  = "https://api.thunderinsights.dk/v1/units/"

# Paramètres de l'API wtvehiclesapi — on récupère TOUT (premium, pack, squadron)
# pour maximiser la couverture des véhicules observés dans les replays
WT_API_PARAMS_ALL = (
    "limit=500"
    "&excludeKillstreak=false"    # inclut les killstreaks (vehicules récompenses)
    "&excludeEventVehicles=false" # inclut les événements
)

TYPE_MAPPING = {
    "fighter":            "F",
    "bomber":             "B",
    "assault":            "B",
    "utility_helicopter": "H",
    "attack_helicopter":  "H",
    "medium_tank":        "T",
    "tank_destroyer":     "T",
    "spaa":               "AA",
    "heavy_tank":         "T",
    "light_tank":         "L",
}

BOAT_KEYWORDS = frozenset(["boat", "ship"])

ENV_DB_PATH = os.getenv("DATABASE_UNITS", "database/all_units.json")
ENV_IMAGES_VEHICLES = os.getenv("DATABASE_IMAGES_VEHICLES", "images/vehicles")

DEFAULT_OUTPUT    = os.path.abspath(ENV_DB_PATH)
IMAGES_DIR        = Path(os.path.abspath(ENV_IMAGES_VEHICLES))


# ── Helpers réseau ────────────────────────────────────────────────────────────

def _get_json(url: str, timeout: int = 30) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "wrpl-parser/1.0",
                                                "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _download_binary(url: str, dest: Path, timeout: int = 30) -> bool:
    """Télécharge un fichier binaire depuis url vers dest. Retourne True si succès."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wrpl-parser/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception:
        return False


def to_hex_spaced(text: str) -> str:
    return " ".join(f"{ord(c):02X}" for c in text).upper()


# ── Source 1 : wtvehiclesapi ──────────────────────────────────────────────────

def fetch_wt_vehicles(verbose: bool = True) -> dict[str, dict]:
    """
    Récupère tous les véhicules de wtvehiclesapi avec pagination.
    Retourne un dict {identifier: entry}.
    """
    all_vehicles: dict[str, dict] = {}
    page = 0

    if verbose:
        print("  Récupération wtvehiclesapi (tous véhicules)...")

    while True:
        url = f"{WT_API_BASE}?{WT_API_PARAMS_ALL}&page={page}"
        try:
            data = _get_json(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                break  # fin de la pagination
            print(f"  [!] HTTP {e.code} à la page {page} — arrêt", file=sys.stderr)
            break
        except Exception as e:
            print(f"  [!] Erreur page {page}: {e}", file=sys.stderr)
            break

        if not data:
            break

        for v in data:
            if v.get("identifier"):
                all_vehicles[v["identifier"]] = v

        if verbose:
            print(f"      page {page} : {len(data)} véhicules (+{len(all_vehicles)} total)", end="\r")

        page += 1
        time.sleep(0.05)

    if verbose:
        print(f"  ✓ wtvehiclesapi : {len(all_vehicles)} véhicules récupérés")
    return all_vehicles


# ── Source 2 : ThunderInsights ────────────────────────────────────────────────

def fetch_thunder_insights(verbose: bool = True) -> dict[str, dict]:
    """
    Récupère les données ThunderInsights.
    Retourne un dict {unit_name: entry}.
    """
    if verbose:
        print("  Récupération ThunderInsights...")

    try:
        data = _get_json(TI_API_URL)
    except Exception as e:
        print(f"  [!] Erreur ThunderInsights : {e}", file=sys.stderr)
        return {}

    result = {unit["unit_name"]: unit for unit in data if unit.get("unit_name")}

    if verbose:
        print(f"  ✓ ThunderInsights : {len(result)} unités récupérées")
    return result


# ── Fusion ────────────────────────────────────────────────────────────────────

def is_boat(wt_entry: dict, ti_entry: dict | None) -> bool:
    vtype_wt = str(wt_entry.get("vehicle_type", "")).lower()
    vtype_ti = str((ti_entry or {}).get("type", "")).lower()
    return (any(k in vtype_wt for k in BOAT_KEYWORDS) or
            any(k in vtype_ti for k in BOAT_KEYWORDS))


def merge(wt_map: dict[str, dict], ti_map: dict[str, dict],
          use_fallback: bool = True) -> tuple[dict[str, dict], int]:
    """
    Fusionne les deux sources.

    Stratégie :
    - Intersection : véhicule présent dans les DEUX → données complètes
    - Fallback (si use_fallback=True) : véhicule dans une seule source → données partielles
      Ce fallback est crucial pour les véhicules premium/événement
      qui peuvent manquer dans une des deux APIs.

    Chaque entrée contient :
      - url_image  : URL distante de l'image du véhicule (depuis wtvehiclesapi)
      - image_path : chemin local prévu → images/vehicles/[identifier].png
                     (le fichier est téléchargé par download_vehicle_images)
    """
    final: dict[str, dict] = {}
    only_wt = only_ti = both = 0

    # Tous les identifiants connus
    all_ids = set(wt_map) | set(ti_map)

    #print(f"   all identifier : {all_ids}")

    for identifier in all_ids:
        wt  = wt_map.get(identifier)
        ti  = ti_map.get(identifier)

        """if identifier == "a_10a_late":
            print(f"   identifier : {identifier}")
            print(f"   wt identifier : {wt}")
            print(f"   ti identifier : {ti}")
            print(f"   if wt and is_boat(wt, ti) : {True if wt and is_boat(wt, ti) else False}")
            print(f"   if not wt and ti : {True if not wt and ti else False}")
            print(f"   if wt and ti : {True if wt and ti else False}")"""

        # Filtre bateaux
        if wt and is_boat(wt, ti):
            continue
        if not wt and ti:
            ti_type = str(ti.get("type", "")).lower()
            if any(k in ti_type for k in BOAT_KEYWORDS):
                continue

        if wt and ti:
            # Fusion complète
            vehicle_full_type = wt.get("vehicle_type") or ti.get("type", "")
            images_block = wt.get("images") or {}
            url_image = images_block.get("image") if isinstance(images_block, dict) else None

            # --- Nettoyage du full_name ---
            raw_full_name = ti.get("shop_name") or identifier
            # On ne garde que : Lettres (incluant accents), Chiffres, Espaces, Tirets, Parenthèses, Points, Slashs
            # On exclut les symboles comme ◔, ◊, ▂, ◄, ▄, etc.
            clean_full_name = re.sub(r'[^a-zA-Z0-9À-ÿ\s\-\(\)\.\/]', '', raw_full_name).strip()
            # ------------------------------

            final[identifier] = {
                "unit_full_name": identifier,
                "unit_hex_full_name": to_hex_spaced(identifier),
                "full_name": clean_full_name,  # Nom nettoyé ici
                "country": wt.get("country") or "",
                "vehicle_full_type": vehicle_full_type,
                "vehicle_type": TYPE_MAPPING.get(vehicle_full_type, "?"),
                "realistic_ground_br": wt.get("realistic_ground_br"),
                "is_premium": wt.get("isPremium", False),
                "is_pack": wt.get("isPack", False),
                "is_squadron": wt.get("isSquadronVehicle", False),
                "url_image": url_image,
                "image_path": f"images/vehicles/{identifier}.png" if url_image else None,
            }
            both += 1

        if wt and not ti:
            vehicle_full_type = wt.get("vehicle_type") or ""
            images_block = wt.get("images") or {}
            url_image = images_block.get("image") if isinstance(images_block, dict) else None

            final[identifier] = {
                "unit_full_name": identifier,
                "unit_hex_full_name": to_hex_spaced(identifier),
                "full_name": "",
                "country": wt.get("country") or "",
                "vehicle_full_type": vehicle_full_type,
                "vehicle_type": TYPE_MAPPING.get(vehicle_full_type, "?"),
                "realistic_ground_br": wt.get("realistic_ground_br"),
                "is_premium": wt.get("isPremium", False),
                "is_pack": wt.get("isPack", False),
                "is_squadron": wt.get("isSquadronVehicle", False),
                "url_image": url_image,
                "image_path": f"images/vehicles/{identifier}.png" if url_image else None,
            }
            both += 1


    return final, both


# ── Téléchargement des images ─────────────────────────────────────────────────

def download_vehicle_images(db: dict[str, dict],
                             images_dir: Path = IMAGES_DIR,
                             skip_existing: bool = True,
                             verbose: bool = True) -> None:
    """
    Télécharge les images PNG de chaque véhicule dans images_dir.
    Le fichier est nommé [identifier].png.

    Args:
        db           : dictionnaire de véhicules produit par merge()
        images_dir   : dossier de destination (créé si inexistant)
        skip_existing: si True, ignore les fichiers déjà présents sur disque
        verbose      : affiche la progression
    """
    images_dir.mkdir(parents=True, exist_ok=True)

    total    = len(db)
    ok = skipped = missing_url = failed = 0

    if verbose:
        print(f"\n  Téléchargement des images → {images_dir}")

    for i, (identifier, entry) in enumerate(db.items(), 1):
        url = entry.get("url_image")
        dest = images_dir / f"{identifier}.png"

        if not url:
            missing_url += 1
            continue

        if skip_existing and dest.exists():
            skipped += 1
            if verbose:
                print(f"  [{i:>5}/{total}] ⏭  {identifier} (déjà présent)", end="\r")
            continue

        success = _download_binary(url, dest)
        if success:
            ok += 1
        else:
            failed += 1
            if verbose:
                print(f"\n  [!] Échec téléchargement : {identifier}  ({url})", file=sys.stderr)

        if verbose:
            print(f"  [{i:>5}/{total}] {'✓' if success else '✗'}  {identifier:<50}", end="\r")

        # Petite pause pour ne pas surcharger le serveur
        time.sleep(0.02)

    if verbose:
        print()  # newline après le \r
        print(f"  Images : {ok} téléchargées | {skipped} déjà présentes "
              f"| {missing_url} sans URL | {failed} échecs")


# ── Rapport de couverture ─────────────────────────────────────────────────────

def coverage_report(db: dict[str, dict]) -> None:
    from collections import Counter
    by_type    = Counter(v["vehicle_type"]    for v in db.values())
    by_country = Counter(v["country"]         for v in db.values() if v["country"])
    premium    = sum(1 for v in db.values() if v.get("is_premium"))
    pack       = sum(1 for v in db.values() if v.get("is_pack"))
    squadron   = sum(1 for v in db.values() if v.get("is_squadron"))

    print(f"\n  Par type     : {dict(sorted(by_type.items()))}")
    print(f"  Par nation   : {dict(by_country.most_common(10))}")
    print(f"  Premium      : {premium}  |  Pack : {pack}  |  Squadron : {squadron}")

    # Véhicules connus comme apparaissant dans les replays
    REPLAY_SAMPLES = [
        "ju-288c", "bi", "a7m2", "germ_panther_II", "ussr_t_44_100",
        "germ_flakpanzer_V_Coelian", "it_fiat_6616_cockerill",
        "spitfire_f24", "us_t26e5",
    ]
    found = sum(1 for v in REPLAY_SAMPLES if v in db)
    print(f"\n  Couverture véhicules replay : {found}/{len(REPLAY_SAMPLES)}")
    for vid in REPLAY_SAMPLES:
        e = db.get(vid)
        if e:
            print(f"    ✓ {vid:<40} {e['full_name']}  br={e['realistic_ground_br']}")
        else:
            print(f"    ✗ {vid:<40} absent (premium/événement non couvert par les APIs)")


# ── Main ──────────────────────────────────────────────────────────────────────

def build(output: Path,
          use_fallback: bool = True,
          download_images: bool = True,
          skip_existing_images: bool = True,
          verbose: bool = True) -> int:
    print("\nConstruction de all_units.json...")

    wt_map = fetch_wt_vehicles(verbose=verbose)
    if not wt_map:
        print("✗ Impossible de récupérer les données wtvehiclesapi", file=sys.stderr)
        return 1

    ti_map = fetch_thunder_insights(verbose=verbose)
    # ThunderInsights optionnel — si absent on continue avec les données WT seules

    db, n_both = merge(wt_map, ti_map, use_fallback=use_fallback)

    print(f"\n  Fusion : {n_both} des deux sources")
    print(f"  Total  : {len(db)} véhicules")

    if verbose:
        coverage_report(db)

    # ── Téléchargement des images ──────────────────────────────────────────────
    if download_images:
        download_vehicle_images(
            db,
            images_dir=IMAGES_DIR,
            skip_existing=skip_existing_images,
            verbose=verbose,
        )

    # ── Sauvegarde JSON ────────────────────────────────────────────────────────
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    size_kb = output.stat().st_size // 1024
    print(f"\n✓ Sauvegardé : {output}  ({size_kb} KB)")
    print("  Place all_units.json dans le même dossier que wrpl_parser_v14.py")
    print("  puis lance : python wrpl_parser_v14.py <replay> --enrich")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Construit all_units.json depuis les APIs WT")
    ap.add_argument("--output",       metavar="FILE", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--no-fallback",  action="store_true",
                    help="Strict : garde seulement les véhicules présents dans les DEUX sources")
    ap.add_argument("--no-images",    action="store_true",
                    help="Désactive le téléchargement des images PNG")
    ap.add_argument("--redownload",   action="store_true",
                    help="Retélécharge les images même si elles existent déjà")
    ap.add_argument("--verbose",      action="store_true")
    args = ap.parse_args()
    sys.exit(build(
        Path(args.output),
        use_fallback=not args.no_fallback,
        download_images=not args.no_images,
        skip_existing_images=not args.redownload,
        verbose=args.verbose,
    ))


if __name__ == "__main__":
    main()
