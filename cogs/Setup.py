import nextcord
from nextcord.ext import commands

from views.setup_views import SetupView

class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.Cog.listener()
    async def on_ready(self):
        print("[Setup Cog]     Le Cog est prêt!")

    @nextcord.slash_command(
        name="setup",
        description="Configurer le bot",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def setup(self, interaction: nextcord.Interaction):
        print(f"Setup: {interaction.client.get_guild(interaction.guild_id)}")
        view = SetupView(self.bot.get_guild(interaction.guild_id))

        await interaction.response.send_message(
            embed=view.build_embed(),
            view=view,
            ephemeral=True
        )

def setup(bot):
    bot.add_cog(Setup(bot))