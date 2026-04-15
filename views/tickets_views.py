import nextcord
from utils.buttons.tickets_buttons import (YesButton, NoButton, OpenTicket, CloseTicket, RecruitementTicket,
                                           IssuesTicket, SuggestTicket, AbsentTicket, UrlFormularyButton, BackTicket)
from database.db_tickets import TicketsDB, Ticket

class OpenTicketsView(nextcord.ui.View):
    STEPS = [
        "choices_ticket",
        "close_ticket",
        "confirmation_close_ticket",
        "cancel_ticket",
    ]

    TITLES = [
        "Demande de recruitement",
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
            self.add_item(RecruitementTicket(db=self.db))
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

        if reason_idx == 0:
            self.add_item(UrlFormularyButton())
            embed1 = nextcord.Embed(
                title=f"{title} | {member}",
                description="Bienvenue à la PYTHON, on t'invite à remplir le formulaire, disponible depuis "
                            "l'en-tete de l'embed ou via le bouton - Apposer la candidature",
                url="https://docs.google.com/forms/d/e/1FAIpQLSe78vzCSrXA4c_t556UmeMJOA-ajl9-h1Lwrc01C7PgOVkmkA/viewform",
                color=nextcord.Color.dark_blue()
            )

            embed2 = nextcord.Embed(
                title=f"La PYTHON 🐍 est un escadron francophone soudé, dynamique, et orienté coordination.",
                description=f"",
                color=nextcord.Color.dark_blue()
            )

            embed2.add_field(
                name="🎯 | Notre objectif:",
                value="🕹️ Jouer inteligemment, progresser ensemble et dominer en batailles d’escadron !\n"
                      "⚔️ Coordination, progression et top classement SQB à terme\n"
                      "✅ Bonus d’EXP escadron fréquent [véhicules d’escadron]\n",
                inline=False
            )

            embed2.add_field(
                name="👁️ | Notre vision:",
                value="La synergie fait la force.",
                inline=False
            )

            embed2.add_field(
                name="📋 | Chez la PYTHON, on privilégie:",
                value="👥 Le jeu d’équipe structuré\n"
                      "🗣️ Une bonne ambiance en vocal\n"
                      "🫡 Le respect et l’entraide comme fondamentaux\n",
                inline=False
            )

            embed2.add_field(
                name="💬 | Notre discord en bref:",
                value="🐍 Petite communauté volontaire, active & soudée\n"
                      "🎙️ Micro et vocal actifs pendant les SQB\n"
                      "🛡️ Entraide pour progresser, dans la bonne humeur\n"
                      "🔥 Events réguliers (SQB, training)\n"
                      "🎖️ Esprit semi-compétitif\n",
                inline=False
            )

            embed2.add_field(
                name="🐍 | Nos attentes dans l'escadron PYTHON:",
                value="👥 Participation régulière en SQB attendue\n"
                      "🎮 Parfait pour les joueurs motivés qui veulent jouer en équipe\n",
                inline=False
            )

            embed2.add_field(
                name="🔎 | Le profil idéal:",
                value="👥 Joueur qui a envie de jouer en escouade\n"
                      "🗣️ A l’aise en vocal / respectueux / réactif\n",
                inline=False
            )

            embed2.add_field(
                name="📊 | Nos critères pour candidater:",
                value="2️⃣ Avoir au minimum 2 nations avec RANG V débloqués (Tank ou Avion)\n"
                      "🥇 Être actif au moins 1300 Points d'activité en SQB pour ta première saison\n"
                      "👥 S’engager à respecter l’ambiance du groupe\n",
                inline=False
            )

            embed2.add_field(
                name="📩 | Prêt à rentrer dans la tanière ?",
                value="**Je t'invite à cliquer sur le bouton, 'Apposer la candidature' pour poursuivre**\n"
                      "Une question ? Une hésitation ? Passe dire bonjour, on ne mord pas (enfin… pas toujours 🐍)",
                inline=False
            )

            embed3 = nextcord.Embed(
                title=f"Système de sauvegarde/fermeture de ticket",
                description="Fermer le ticket - Enregistre automatiquement + Ferme le ticket"
                            "\nAnnuler - Annule le ticket",
                color=nextcord.Color.dark_red()
            )

            embed3.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

            return [embed1, embed2]

        elif reason_idx == 3:
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
