import nextcord

from utils.buttons.setup_buttons import NextButton, PreviousButton, CancelButton, EndButton
from utils.selects.setup_selects import CategorySelect, PilotRoleSelect, LeaderRoleSelect, LogChannelSelect

class SetupView(nextcord.ui.View):

    STEPS = [
        "category",
        "pilot_role",
        "leader_role",
        "log_channel",
        "final"
    ]

    def __init__(self, guild):
        super().__init__(timeout=300)

        self.guild = guild
        self.step_index = 0
        self.error_page = None

        self.data = {
            "category": None,
            "pilot_role": None,
            "leader_role": None,
            "log_channel": None
        }

        self.names = {
            "category": None,
            "pilot_role": None,
            "leader_role": None,
            "log_channel": None
        }

        self.update_components()

    #async def interaction_check(self, interaction: nextcord.Interaction) -> bool:
        #return interaction.user.guild_permissions.administrator

    def update_components(self):

        self.clear_items()

        step = self.STEPS[self.step_index]

        if step == "category":
            self.add_item(CategorySelect())

        elif step == "pilot_role":
            self.add_item(PilotRoleSelect())

        elif step == "leader_role":
            self.add_item(LeaderRoleSelect())

        elif step == "log_channel":
            self.add_item(LogChannelSelect())

        elif step == "final":
            self.add_item(EndButton())

        # Bouton retour
        if self.step_index > 0:
            self.add_item(PreviousButton())

        # Bouton suivant
        if step != "final":
            self.add_item(NextButton())
            self.add_item(CancelButton())

    def build_embed(self):

        step = self.STEPS[self.step_index]
        error_page = self.error_page

        if error_page is not None:
            embed = nextcord.Embed(
                title="⚙️ Configuration du bot",
                description="Suivez les étapes pour configurer le bot.",
                color=nextcord.Color.dark_red()
            )

            embed.add_field(
                name="Étape actuelle",
                value=step.replace("_", " ").title(),
                inline=False
            )

            embed.add_field(
                name="Progression",
                value=f"{self.step_index + 1}/{len(self.STEPS)}",
                inline=False
            )

            embed.add_field(
                name="⚠️ ERREUR DANS LA SAISIE",
                value=f" ",
                inline=False
            )

            embed.set_footer(text="Assistant de configuration")

            self.error_page = None

            return embed

        embed = nextcord.Embed(
            title="⚙️ Configuration du bot",
            description="Suivez les étapes pour configurer le bot.",
            color=nextcord.Color.blurple()
        )

        embed.add_field(
            name="Étape actuelle",
            value=step.replace("_", " ").title(),
            inline=False
        )

        embed.add_field(
            name="Progression",
            value=f"{self.step_index+1}/{len(self.STEPS)}",
            inline=False
        )

        embed.set_footer(text="Assistant de configuration")

        if step == "final":
            embed.add_field(
                name="Résumé de la configuration",
                value=(
                    f"Catégorie : {self.names['category']}\n"
                    f"Rôle pilote : <{self.names['pilot_role']}>\n"
                    f"Rôle leader : {self.names['leader_role']}\n"
                    f"Logs : {self.names['log_channel']}"
                ),
                inline=False
            )

            embed.set_footer(text="Cliquez sur 'Fin' pour confirmer la configuration.")

        return embed