import os
import nextcord
from pathlib import Path
from dotenv import load_dotenv
from nextcord.ext import commands

load_dotenv()

#################################################################
# INTENTS BOT

intents = nextcord.Intents.default()
intents.message_content = True  # Permet à votre bot de lire le contenu des messages
intents.reactions = True  # Permet à votre bot de gérer les émojis (ajouter et supprimer des réactions)
intents.members = True
intents.guilds = True
intents.guild_reactions = True
intents.guild_messages = True
intents.guild_typing = True
intents.moderation = True
intents.typing = True
intents.voice_states = True
intents.presences = True
intents.messages = True

#################################################################
# BOT

bot = commands.Bot(command_prefix='!', intents=intents)

#################################################################
# CONFIG

class Config:
    # Cookies warthunder.com (DevTools → Application → Cookies → warthunder.com)
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")

    WT_CF_CLEARANCE: str = os.getenv("WT_CF_CLEARANCE", "")
    WT_CSRF: str = os.getenv("WT_CSRF", "")
    WT_IDENTITY_TOKEN: str = os.getenv("WT_IDENTITY_TOKEN", "")
    WT_IDENTITY_SID: str = os.getenv("WT_IDENTITY_SID", "")
    WT_SESSION_ID: str = os.getenv("WT_SESSION_ID", "")

    # Paramètres polling
    POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL_SECONDS", ""))
    DB_PATH: str = os.getenv("DB_PATH", "")

#################################################################