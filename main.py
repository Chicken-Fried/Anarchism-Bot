import os
import asyncio
import nextcord
import logging
import traceback

logging.basicConfig(level=logging.DEBUG, format='%(name)s: %(message)s')

from nextcord.ext import commands
from core.config import *

from views.tickets_views import OpenTicketsView
from views.applications_views import OpenApplicationsView
from views.thread_views import ThreadView

from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv('TOKEN')
COGS  = os.getenv('COGS')

# ── Intégration SQB poller ────────────────────────────────────────────────
from wrpl.db_replay import ReplayDB
from wrpl.poller    import WTPoller

db_replays     = ReplayDB()
bot.db_replays = db_replays
poller        = WTPoller(db=db_replays)

# ─────────────────────────────────────────────────────────────────────────
from database.db_tickets import TicketsDB
db_tickets     = TicketsDB()
bot.db_tickets = db_tickets

# ─────────────────────────────────────────────────────────────────────────
from database.db_informations import InformationDB
db_infos     = InformationDB()
bot.db_infos = db_infos

@bot.command()
@commands.is_owner()
async def sync(ctx):
    print("Synchronisation en cours...")
    await bot.sync_all_application_commands()
    await ctx.send("✅ Commandes synchronisées !")

@bot.event
async def on_ready():
    #await bot.sync_all_application_commands()
    bot.add_view(OpenTicketsView(db=bot.db_tickets))
    bot.add_view(OpenApplicationsView(db=bot.db_tickets))
    bot.add_view(ThreadView())
    print(f'{bot.user.name} est en ligne!')

    # ── Démarrage du poller SQB ───────────────────────────────────────────
    """try:
        await poller.start()
        bot.loop.create_task(
            poller.poll_loop(interval_seconds=120),
            name="sqb_poller",
        )
        print("Poller SQB démarré.")
    except Exception as e:
        print(f"Poller SQB non démarré : {e}")
        print("Lance 'python wrpl/setup_session.py' pour initialiser la session WT.")"""
    # ─────────────────────────────────────────────────────────────────────


@bot.event
async def on_error(event, *args, **kwargs):
    print(f'Erreur, événement(s): {event}!')
    logging.error(f"Erreur dans l'événement {event}", exc_info=True)
    if args and not kwargs:
        for arg in args:
            print(arg)
    if not args and kwargs:
        for key, value in list(kwargs.items()):
            print(key, value, sep=" :")


@bot.event
async def on_disconnect():
    print(f"{bot.user.name} - connexion interrompue !")


@bot.event
async def on_close():
    print(f"{bot.user.name} s'est éteint!")

    # ── Arrêt propre du poller ────────────────────────────────────────────
    #await poller.stop()
    # ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    for filename in os.listdir(COGS):
        if filename.endswith('.py') and not filename.startswith('_'):
            bot.load_extension(f'{COGS}.{filename[:-3]}')
    bot.run(TOKEN)
