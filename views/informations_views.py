import locale

import nextcord
import datetime

from babel.dates import format_date
from typing import List, Tuple, Optional
from datetime import datetime, date

from database.models.informations_class import SchedulerSqb, VehicleTable


class InformationsView(nextcord.ui.View):
    STEPS = [
        "sqb_schedular",
        "vehicles_viewer",
        "meta_vehicles_viewer",
        "find_vehicles_viewer",
        "cancel_vehicles_viewer"
    ]

    TITLES = [
        "Afficheur générique de véhicules",
        "Afficheur meta de véhicules",
        "Trouver un véhicule",
        "Revenir en arrière"
    ]

    def __init__(self):
        super().__init__(timeout=None)

        self.step_index = {}
        self.error_page = None

        self.schedular_sqb = None
        self.br_actual = None
        self.voice_channels = {}

        self.data = {}

        #self.add_item(OpenTicket())

    def update_components(self, interaction: nextcord.Interaction):
        self.clear_items()

        step = self.STEPS[self.step_index[interaction.user.name]]

        """if step == "choices_ticket":
            self.add_item(RecruitementTicket())
            self.add_item(SuggestTicket())
            self.add_item(IssuesTicket())
            self.add_item(AbsentTicket())
            #self.add_item(CancelTicket())

        if step == "close_ticket":
            self.add_item(CloseTicket())
            self.add_item(BackTicket())
            #self.add_item(CancelTicket())

        if step == "confirmation_close_ticket":
            self.add_item(YesButton())
            self.add_item(NoButton())"""

    def sqb_scheduler_update(self, schedular_sqb: Optional[List[SchedulerSqb]]) -> List[nextcord.Embed]:
        """
        Retourne un embed en lien avec le calendrier SQB, si le paramètre fournit possède la liste

        :param: schedular_sqb Optional[List[SchedulerSqb]]: Possède les informations du calendrier SQB sinon None
        :return: List[nextcord.Embed]:
        """
        if not schedular_sqb:
            embed1 = nextcord.Embed(
                title=f"ERREUR - Afficheur du calendrier SQB inexistant",
                description=f"⚠️ Afficheur inexistant",
                color=nextcord.Color.dark_red()
            )
            return [embed1]

        first_month = format_date(schedular_sqb[0].start_date, 'MMMM', locale='fr')
        last_month = format_date(schedular_sqb[-1].start_date, 'MMMM', locale='fr')

        embed1 = nextcord.Embed(
            title=f"Afficheur du calendrier SQB - Saison {first_month.capitalize()}-{last_month.capitalize()}",
            color=0xBA121A
        )

        now = date.today()

        for schedule_week in schedular_sqb:
            start_date = schedule_week.start_date_obj
            end_date = schedule_week.end_date_obj

            if start_date <= now <= end_date:
                self.br_actual = str(schedule_week.br)

            embed1.add_field(name=f"BR: {schedule_week.br}",
                             value=f"{start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')}", inline=False)
        return [embed1]

    def vehicles_viewer(self, vehicles_table: List[VehicleTable]) -> List[nextcord.Embed]:
        """
        Afficheur dynamique des véhicules aux BR que l'utilisateur à sélectionner
        :param:
            vehicles_table List[VehicleTable]: Possèdes les informations des véhicules en lien avec le BR,
        utilisable en SQB
        :return:
            List[nextcord.Embed]:
        """
        return
