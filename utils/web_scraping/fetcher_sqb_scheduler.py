import datetime
from unittest import result

import requests
import re

from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from datetime import datetime



def is_url(url) -> bool | None:
    """
    Retourne une valeur booléenne si l'URL est un URL existant ou pas.

    Args:
        url (str): URL dont l'utilisateur souhiate effectuer une requete

    Returns:
        bool: True si URL existe ou False sinon, None en cas d'erreur système

    Raises:
        TypeError: Si le type de l'url est incorrect
        ValueError: Si l'url est pas au bon format
        Exception: Si une quelconque exception ou erreur est présent, ceci est affichée
    """

    try:
        if not isinstance(url, str):
            print(f"[Web_scraping Fetcher_sqb_scheduler]    Is_url: "
                  f"Erreur - Type invalide: {type(url).__name__}")
            return False
        if not url or not url.strip():
            print(f"[Web_scraping Fetcher_sqb_scheduler]    Is_url: "
                  f"Erreur - URL vide ou invalide")
            return False

        result = urlparse(url)

        if all([result.scheme, result.netloc]):
            print(f"[Web_scraping Fetcher_sqb_scheduler]    Is_url: "
                  f"URL valide:{url}")
            return True

        else:
            missing = []
            if not result.scheme:
                missing.append("scheme (http/https)")
            if not result.netloc:
                missing.append("netloc (domaine)")

            print(f"[Web_scraping Fetcher_sqb_scheduler]    Is_url: "
                  f"Erreur - URL invalide - Manque:{', '.join(missing)}")
            return False

    except TypeError as e:
        print(f"[Web_scraping Fetcher_sqb_scheduler]    Is_url: "
              f"Erreur - TypeError: {e}")
        return None

    except ValueError as e:
        print(f"[Web_scraping Fetcher_sqb_scheduler]    Is_url: "
              f"Erreur - ValueError: {e}")
        return None

    except Exception as e:
        print(f"[Web_scraping Fetcher_sqb_scheduler]    Is_url: "
              f"Erreur - Erreur inconnue: {type(e).__name__} - {e}")
        return None

def url_page() -> Optional[str]:
    """
    Teste si le site internet est fonctionnel
    :return:
        str | None: Retourne l'url du site internet, sinon None si l'URL ne fonctionne pas
    """
    url = "https://forum.warthunder.com/t/season-schedule-for-squadron-battles/4446"
    if not is_url(url):
        return None
    return url

def process_scheduler_sqb(lines) -> List[Tuple[str, datetime, datetime]]:
    """
    Traite les lignes HTML pour extraire les dates SQB
    :param
        lines: Listes de balise <p> BeautifulSoup
    :return:
        List[Tuple[str, datetime, datetime]]: Liste des dates SQB, avec [BR, Début date, Fin date]
    """
    pattern = r"(\d+\.\d+)\s*\((\d{2}\.\d{2})\s*—\s*(\d{2}\.\d{2})\)"
    current_year = datetime.now().year
    results: List[Tuple[str, datetime, datetime]] = []

    for line in lines:
        text = line.get_text(separator="\n").strip()

        try:
            match = re.search(pattern, text)

            #Condition1: recherche le pattern dans la ligne du texte
            if match:
                br = match.group(1)
                start_str = match.group(2)
                end_str = match.group(3)

                start_date = datetime.strptime(f"{start_str}.{current_year}", "%d.%m.%Y")
                end_date = datetime.strptime(f"{end_str}.{current_year}", "%d.%m.%Y")

                #Condition2: Vérifie que les dates se précèdent entre eux
                if end_date <= start_date:
                    print(f"[Web_scraping Fetcher_sqb_scheduler]    Process_scheduler_sqb: "
                          f"Erreur - Date invalide pour BR {br}: "
                          f"Fin-({end_date}) avant Début-({start_date})")
                    continue

                results.append((br, start_date, end_date))

            else:
                print(f"[Web_scraping Fetcher_sqb_scheduler]    Process_scheduler_sqb: "
                      f"Erreur - Aucune correspondance trouvée sur la ligne")

        except ValueError as e:
            print(f"[Web_scraping Fetcher_sqb_scheduler]    Process_scheduler_sqb: "
                  f"Erreur - ValueError: {e}")
            continue

    return results


def initialize_sqb_scheduler() -> List[Tuple[str, datetime, datetime]]:
    """
    Initialise le calendrier SQB en récupérant les données du forum.
    :return:
        List[List[br, start_date, end_date]] ou [] en cas d'erreur
    """

    scheduler_sqb: List[Tuple[str, datetime, datetime]] = []

    try:
        url = url_page()

        #Condition1: Si URL n'existe pas, alors on fournit une liste vide
        if not url:
            print(f"[Web_scraping Fetcher_sqb_scheduler]    Initialize_sqb_scheduler: "
                  f"Erreur - URL invalide")
            return scheduler_sqb

        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                break

            except requests.exceptions.Timeout as e:
                print(f"[Web_scraping Fetcher_sqb_scheduler]    Initialize_sqb_scheduler: "
                      f"Erreur - Timeout [Tentative {attempt + 1}/{max_retries}]: {e}")
                if attempt == max_retries - 1:
                    raise

            except requests.exceptions.RequestException as e:
                print(f"[Web_scraping Fetcher_sqb_scheduler]    Initialize_sqb_scheduler: "
                      f"Erreur - Erreur HTTP [Tentative {attempt + 1}/{max_retries}]: {e}")
                if attempt == max_retries - 1:
                    return scheduler_sqb

        soup = BeautifulSoup(response.text, "html.parser")
        cooked_div = soup.find_all("div", {"class": "post"})

        if not cooked_div:
            print(f"[Web_scraping Fetcher_sqb_scheduler]    Initialize_sqb_scheduler: "
                  f"Erreur - Structure HTML non trouvée [Classe .post]")
            return scheduler_sqb

        lines = cooked_div.find_all("p")

        results = process_scheduler_sqb(lines)
        scheduler_sqb.extend(results)

        print(f"[Web_scraping Fetcher_sqb_scheduler]    Initialize_sqb_schedular: "
              f"Calendrier SQB initialisé avec {len(scheduler_sqb)} semaines de saison")

    except Exception as e:
        print(f"[Web_scraping Fetcher_sqb_scheduler]    Initialize_sqb_schedular: "
              f"Erreur - Erreur inattendue: {type(e).__name__} - {e}")
        return scheduler_sqb

    return scheduler_sqb