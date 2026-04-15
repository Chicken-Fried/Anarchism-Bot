"""
TODO: Afficher dans un channel textuel avec une alerte/ping aux staffs/admin les critical error du bot/système
"""

import nextcord
from nextcord.ext import commands


class CriticalError(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("[CriticalError Cog]     Le Cog est prêt!")



def setup(bot):
    bot.add_cog(CriticalError(bot))