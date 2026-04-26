import nextcord
from utils.buttons.tickets_buttons import (YesButton, NoButton, OpenTicket, CloseTicket,
                                           IssuesTicket, SuggestTicket, AbsentTicket, BackTicket)
from database.db_tickets import TicketsDB, Ticket

class OpenTicketsView(nextcord.ui.View):
    STEPS = [
        "choices_ticket",
        "close_ticket",
        "confirmation_close_ticket",
        "cancel_ticket",
    ]

    TITLES = [
        "Introduction de suggestion",
        "Faire part d'un problème",
        "Introduction d'une absence"
    ]

    def __init__(self, db: TicketsDB):
        super().__init__(timeout=None)

        self.step_index = {}
        self.error_page = None
        self.db = db

        self.add_item(OpenTicket(db=self.db))

    def update_components(self, interaction: nextcord.Interaction, ticket: Ticket):
        self.clear_items()

        step = self.STEPS[ticket.step]

        if step == "choices_ticket":
            self.add_item(SuggestTicket(db=self.db))
            self.add_item(IssuesTicket(db=self.db))
            self.add_item(AbsentTicket(db=self.db))

        if step == "close_ticket":
            self.add_item(CloseTicket(db=self.db))
            self.add_item(BackTicket(db=self.db))

        if step == "confirmation_close_ticket":
            self.add_item(YesButton(db=self.db))
            self.add_item(NoButton(db=self.db))


    def embd_open_ticket(self):
        error_page = self.error_page

        if error_page is not None:
            embed = nextcord.Embed(
                title="🧾 Ouvrez un ticket !",
                description="Une erreur est apparut lors de l'ouverture du ticket !",
                color=nextcord.Color.dark_red()
            )

            embed.add_field(
                name="Démarche à effectuer pour poursuivre :",
                value="Veuillez contactez le staff pour ouvrir un ticket manuellement.",
                inline=False
            )

            embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

            self.error_page = None

            return [embed]

        embed = nextcord.Embed(
            title="🧾 Ouvrez un ticket !",
            description="En cliquant sur le bouton, un ticket sera ouvert pour vous.",
            color=nextcord.Color.blurple()
        )

        embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

        return [embed]

    def embd_cancel_ticket(self):
        self.clear_items()
        error_page = self.error_page

        if error_page is not None:
            embed = nextcord.Embed(
                title="🧾 ERREUR - ANNULATION TICKET",
                description="Une erreur est apparut lors de la fermeture du ticket !",
                color=nextcord.Color.dark_red()
            )

            embed.add_field(
                name="Démarche à effectuer pour poursuivre :",
                value="Veuillez contactez le staff pour fermer ce ticket.",
                inline=False
            )

            embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

            self.error_page = None

            return [embed]

        embed = nextcord.Embed(
            title="🧾 Annulation du ticket",
            description="Ce ticket a été annulé, et le salon sera bientot fermé."
                        "\nBonne journée/soirée!",
            color=nextcord.Color.blurple()
        )

        embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

        return [embed]

    def embd_choice_reason(self):
        error_page = self.error_page

        if error_page is not None:
            embed = nextcord.Embed(
                title="🧾 ERREUR - OUVERTURE TICKET",
                description="Une erreur est apparut lors de l'ouverture du ticket !",
                color=nextcord.Color.dark_red()
            )

            embed.add_field(
                name="Démarche à effectuer pour poursuivre :",
                value="Veuillez contactez le staff pour ouvrir un ticket manuellement.",
                inline=False
            )

            embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

            self.error_page = None

            return [embed]

        embed = nextcord.Embed(
            title="🧾 Thème du ticket",
            description="Choisissez la raison de l'ouverture du ticket.",
            color=nextcord.Color.dark_blue()
        )

        embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

        return [embed]

    def embd_response_reason(self, ticket: Ticket):
        error_page = self.error_page

        reason_idx = ticket.reason_ticket
        member = ticket.user_name

        title = self.TITLES[reason_idx]

        if error_page is not None:

            embed = nextcord.Embed(
                title="🧾 ERREUR - OUVERTURE TICKET",
                description="Une erreur est apparut lors de l'ouverture du ticket !",
                color=nextcord.Color.dark_red()
            )

            embed.add_field(
                name="Démarche à effectuer pour poursuivre :",
                value="Veuillez contactez le staff pour ouvrir un ticket manuellement.",
                inline=False
            )

            embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

            self.error_page = None

            return [embed]

        if reason_idx == 2:
            self.add_item(AbsentTicket(db=self.db))

            embed1 = nextcord.Embed(
                title=f"{title} | {member}",
                description="Si tu dois être absent un certain temps ou un pendant délai précis.",
                color=nextcord.Color.dark_blue()
            )

            embed1.add_field(
                name="Démarche à effectuer pour poursuivre :",
                value="Je t'invite à écrire la date de début d'absence sous la forme suivante, [JJ/MM/AAAA]."
                      "\nSi le format suivant est incorrect, tu devras le réintroduire",
                inline=False
            )

            embed2 = nextcord.Embed(
                title=f"Système de sauvegarde/fermeture de ticket",
                description="Fermer le ticket - Enregistre automatiquement + Ferme le ticket"
                            "\nAnnuler - Annule le ticket",
                color=nextcord.Color.dark_red()
            )

            embed2.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

            return [embed1, embed2]
        else:
            embed1 = nextcord.Embed(
                title=f"{title} | {member}",
                description="Fais nous part de ta suggestion/ton problème au sein de la team ! Ton avis compte pour nous.",
                color=nextcord.Color.dark_blue()
            )

            embed2 = nextcord.Embed(
                title=f"Système de sauvegarde/fermeture de ticket",
                description="Fermer le ticket - Enregistre automatiquement + Ferme le ticket"
                            "\nAnnuler - Annule le ticket",
                color=nextcord.Color.dark_red()
            )

            embed2.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

            return [embed1, embed2]

    def embd_confirmation(self):
        error_page = self.error_page

        if error_page is not None:
            embed = nextcord.Embed(
                title="🧾 ERREUR - FERMETURE TICKET",
                description="Une erreur est apparut lors de l'ouverture du ticket !",
                color=nextcord.Color.dark_red()
            )

            embed.add_field(
                name="Démarche à effectuer pour poursuivre :",
                value="Insérer la commande appropriée pour fermer le ticket manuellement",
                inline=False
            )

            embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

            self.error_page = None

            return [embed]

        else:
            embed = nextcord.Embed(
                title="🧾 Fermeture du ticket",
                description="Souhaitez vous continuer dans la fermeture du ticket ?",
                color=nextcord.Color.dark_blue()
            )

            embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

            return [embed]


    def embd_y_confirmation(self):
        error_page = self.error_page

        if error_page is not None:
            embed = nextcord.Embed(
                title="🧾 ERREUR - FERMETURE TICKET",
                description="Une erreur est apparut lors de l'ouverture du ticket !",
                color=nextcord.Color.dark_red()
            )

            embed.add_field(
                name="Démarche à effectuer pour poursuivre :",
                value="Insérer la commande appropriée pour fermer le ticket manuellement",
                inline=False
            )

            embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

            self.error_page = None

            return [embed]

        embed = nextcord.Embed(
            title="🧾 Fermeture du ticket",
            description="Le ticket va se fermer et s'enregitrer, veuillez patienter",
            color=nextcord.Color.dark_blue()
        )

        embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

        return [embed]
