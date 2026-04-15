"""
setup_session_server.py — Pour serveur Debian sans GUI.
Utilise Xvfb pour créer un display virtuel.
"""
import asyncio
import os
import subprocess
import signal
from playwright.async_api import async_playwright


async def setup():
    user_data_dir = os.path.join(os.getcwd(), "user_data")
    os.makedirs(user_data_dir, exist_ok=True)

    # Démarrer un display virtuel
    display = ":99"
    xvfb = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "1280x720x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.environ["DISPLAY"] = display
    print(f"Display virtuel démarré ({display})")

    try:
        async with async_playwright() as p:
            print("Lancement du navigateur...")
            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,          # fonctionne grâce à Xvfb
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 720},
            )
            page = context.pages[0] if context.pages else await context.new_page()

            await page.goto(
                "https://warthunder.com/en/tournament/replay/",
                wait_until="domcontentloaded"
            )

            # Connexion automatisée si tu veux éviter le VNC
            # Sinon, utilise VNC pour voir le navigateur (voir ci-dessous)
            print()
            print("=" * 50)
            print("OPTION 1 : Connecte-toi via VNC sur le display :99")
            print("OPTION 2 : Renseigne tes identifiants ci-dessous")
            print("=" * 50)

            email = input("Email War Thunder (laisser vide si tu utilises VNC) : ").strip()

            if email:
                password = input("Mot de passe : ").strip()
                await page.goto("https://login.gaijin.net/", wait_until="domcontentloaded")
                await page.fill('input[type="email"], input[name="login"]', email)
                await page.fill('input[type="password"]', password)

                # Cocher "remember me" si présent
                remember = page.locator('input[type="checkbox"]').first
                if await remember.count() > 0:
                    await remember.check()

                await page.click('button[type="submit"]')
                await page.wait_for_load_state("networkidle", timeout=15000)
                print("Connecté ! Vérification...")
            else:
                print("\nAttends la connexion via VNC, puis appuie sur ENTRÉE.")
                await asyncio.to_thread(input, "\nAppuie sur ENTRÉE quand connecté... ")

            await context.close()

    finally:
        xvfb.send_signal(signal.SIGTERM)
        print("\nSession sauvegardée dans ./user_data/")
        print("Lance maintenant ton bot avec headless=True.")


if __name__ == "__main__":
    asyncio.run(setup())