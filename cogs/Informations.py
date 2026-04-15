import nextcord
import asyncio
from nextcord.ext import commands, tasks
from datetime import datetime

from views.informations_views import InformationsView
from utils.web_scraping.fetcher_sqb_schedular import initialize_sqb_schedular
from database.models.informations_class import SchedulerSqb

class Informations(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.monthly_task.start()
        self.schedular = None


    def cog_unload(self):
        self.monthly_task.cancel()

    @tasks.loop(time=datetime.strptime("01:00", "%H:%M").time())
    async def monthly_task(self):
        """
        S'exécute tous les 1er du mois
        :return:
        """
        now = datetime.now()
        if now.day == 1:
            try:
                print("[Informations Cog]     Automatisation lancée !")
                loop = asyncio.get_event_loop()
                schedular = await loop.run_in_executor(None, initialize_sqb_schedular)
                print("[Informations Cog]     Automatisation réussie. - Mise à jour en cours...") if schedular else (
                    print("[Informations Cog]     Erreur - Automatisation échoué..."))

                if schedular:
                    self.schedular = []
                    for idx, schedule in enumerate(schedular):
                        self.schedular.append(
                            SchedulerSqb(
                                year=now.year,
                                season_num=int(schedular[-1][1].month/2),
                                line_num=idx+1,
                                br=schedule[idx][0],
                                start_date=schedule[idx][1],
                                end_date=schedule[idx][2]
                            )
                        )

            except Exception as e:
                print(f"[Informations Cog]     "
                      f"Erreur - Automatisation échoué | Echec de scrapping : {e}")


    @commands.Cog.listener()
    async def on_ready(self):
        print("[Informations Cog]     Le Cog est prêt!")

    @nextcord.slash_command(
        name="sqb-viewer",
        description="Afficheur dynamique pour afficher les véhicules du BR",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def informations_vehicles(self, interaction: nextcord.Interaction):
        view = InformationsView()

        await interaction.response.send_message(
            embed=view.sqb_scheduler_update(self.schedular),
            view=view,
            ephemeral=True
        )



def setup(bot):
    bot.add_cog(Informations(bot))