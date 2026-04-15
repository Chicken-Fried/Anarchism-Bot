import asyncio
import os
from playwright.async_api import async_playwright


async def seal_session():
    user_data_dir = os.path.join(os.getcwd(), "user_data")
    if not os.path.exists(user_data_dir): os.makedirs(user_data_dir)

    async with async_playwright() as p:
        # On lance un Chrome classique, pas headless
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={'width': 1280, 'height': 720}
        )
        page = context.pages[0]

        print("🌐 Direction la page de login...")
        await page.goto("https://warthunder.com/en/tournament/replay/", wait_until="domcontentloaded")

        print("\n=== ÉTAPES À SUIVRE ===")
        print("1. Connecte-toi (Email + MDP).")
        print("2. COCHE BIEN 'Remember me'.")
        print("3. Une fois connecté, clique sur 'Squadron battle' dans les filtres.")
        print("4. Attends que les replays s'affichent.")
        print("5. REVIENS ICI ET APPUIE SUR ENTREE.")

        # On bloque le script ici
        await asyncio.to_thread(input, "\n👉 Appuie sur ENTREE quand tu vois les replays d'escadrille...")

        # LA PARTIE CRUCIALE : Fermeture propre pour enregistrer les cookies
        print("💾 Sauvegarde de la session en cours...")
        await context.close()
        print("✅ Session scellée ! Tu peux maintenant utiliser le bot en arrière-plan.")


if __name__ == "__main__":
    asyncio.run(seal_session())