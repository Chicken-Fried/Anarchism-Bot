"""
setup_session.py — À lancer UNE SEULE FOIS sur la machine du bot.

Lance Chromium visible, l'utilisateur se connecte à War Thunder,
puis la session est sauvegardée dans ./user_data/ pour le bot.
"""
import asyncio
import os

from pathlib import Path
from playwright.async_api import async_playwright

from dotenv import load_dotenv
load_dotenv()

USER_DATA_PATH = os.getenv("USER_DATA", "user_data")
USER_DATA = os.path.abspath(USER_DATA_PATH)


async def setup():
    os.makedirs(USER_DATA, exist_ok=True)

    async with async_playwright() as p:
        print("Lancement du navigateur...")
        context = await p.chromium.launch_persistent_context(
            USER_DATA,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 720},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto("https://warthunder.com/en/tournament/replay/",
                        wait_until="domcontentloaded")

        print()
        print("=" * 50)
        print("1. Connecte-toi sur la page War Thunder.")
        print("2. Coche 'Remember me' / 'Se souvenir de moi'.")
        print("3. Attends que la liste des replays soit visible.")
        print("4. Reviens ici et appuie sur ENTRÉE.")
        print("=" * 50)

        await asyncio.to_thread(input, "\nAppuie sur ENTRÉE quand connecté... ")
        await context.close()
        print("\nSession sauvegardée dans ./user_data/ !")
        print("Tu peux maintenant lancer le bot.")


if __name__ == "__main__":
    asyncio.run(setup())
