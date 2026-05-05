import nextcord
from utils.buttons.applications_buttons import (OpenApplication, CloseTicket, YesButton, NoButton,
                                                UrlFormularyButton)
from database.db_tickets import TicketsDB, Ticket

class OpenApplicationsView(nextcord.ui.View):
    STEPS = [
        "application_ticket",
        "confirmation_close_ticket"
    ]

    def __init__(self, db: TicketsDB):
        super().__init__(timeout=None)

        self.step_index = {}
        self.error_page = None
        self.db = db

        self.add_item(OpenApplication(db=self.db))

    def update_components(self, interaction: nextcord.Interaction, ticket: Ticket):
        self.clear_items()

        step = self.STEPS[ticket.step]

        if step == "application_ticket":
            self.add_item(UrlFormularyButton())
            self.add_item(CloseTicket(db=self.db))

        if step == "confirmation_close_ticket":
            self.add_item(YesButton(db=self.db))
            self.add_item(NoButton(db=self.db))

    def embd_open_application(self):
        error_page = self.error_page

        if error_page is not None:
            embed = nextcord.Embed(
                title="🧾 Poser une Candidature !",
                description="Une erreur est apparut lors de l'ouverture de la candidature !",
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

        embed1 = nextcord.Embed(
            title="🧾 Poser une Candidature !",
            description="🐍 - Bienvenue à la PYTHON ! Nous sommes un escadron francophone à la quête de l'excellence "
                        "pour atteindre le sommet ! Nous sommes ravis que tu nous es choisi pour ta candidature.\n",
            color=nextcord.Color.dark_purple()
        )

        embed1.add_field(
            name="📝 Étape 1",
            value="Je t'invite à lire nos conditions, ci-dessous, avant de poursuivre"
        )

        embed2 = nextcord.Embed(
            title="🐍 L'Escadron PYTHON",
            description="Découvre notre univers et ce que nous attendons de nos membres.",
            color=nextcord.Color.dark_blue()
        )

        embed2.add_field(
            name="🎯 | Notre Mission",
            value=(
                "> *La synergie fait la force.*\n"
                "• **Objectif :** Jouer intelligemment et dominer les batailles d’escadron.\n"
                "• **Engagement :** Progression constante et top classement SQB."
            ),
            inline=False
        )

        # Bloc 2 : L'ambiance & Le Discord
        embed2.add_field(
            name="🤝 | Notre ADN",
            value=(
                "**Ce que nous privilégions :**\n"
                "• Jeu d’équipe structuré & entraide.\n"
                "• Ambiance vocale active (SQB, training).\n"
                "• Respect et esprit semi-compétitif."
            ),
            inline=False
        )

        # Bloc 3 : Critères de recrutement (Le plus important)
        embed2.add_field(
            name="📋 | Critères & Profil",
            value=(
                "**Prérequis techniques :**\n"
                "• Min. **2 nations RANG V** débloquées (Tank/Avion).\n"
                "• **1300+ points d'activité** dès la première saison.\n\n"
                "**Profil recherché :**\n"
                "• Joueur d'escouade, réactif et respectueux."
            ),
            inline=False
        )

        # Bloc 4 : Conclusion / Contact
        embed2.add_field(
            name="📩 | Prêt à nous rejoindre ?",
            value="Alors clique sous le bouton, ci-dessous '📥 Poser une candidature'",
            inline=False
        )

        embed2.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

        return [embed1, embed2]

    def embd_response(self, ticket: Ticket):
        error_page = self.error_page

        member = ticket.user_name

        if error_page is not None:

            embed = nextcord.Embed(
                title="❌ ERREUR - OUVERTURE CANDIDATURE",
                description="Une erreur est apparut lors de l'ouverture de la candidature !",
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

        embed1 = nextcord.Embed(
            title=f"👋 Bienvenue, {member} !",
            description=(
                "Ta candidature commence ici. Pour nous rejoindre, tu dois impérativement "
                "remplir le formulaire ci-dessous :"
            ),
            url="https://docs.google.com/forms/d/e/1FAIpQLSe78vzCSrXA4c_t556UmeMJOA-ajl9-h1Lwrc01C7PgOVkmkA/viewform",
            color=nextcord.Color.dark_blue()
        )

        embed1.add_field(
            name="📝 Étape 2",
            value="Clique sur le bouton **'Apposer la candidature'** ou utilise le lien ci-dessus."
        )

        embed1.add_field(
            name="📝 | Je te remet nos conditions d'adhésion, ci dessous, bonne lecture !",
            value="",
            inline=False
        )

        embed2 = nextcord.Embed(
            title="🐍 L'Escadron PYTHON",
            description="Découvre notre univers et ce que nous attendons de nos membres.",
            color=nextcord.Color.dark_blue()
        )

        # Bloc 1 : Vision & Objectifs
        embed2.add_field(
            name="🎯 | Notre Mission",
            value=(
                "> *La synergie fait la force.*\n"
                "• **Objectif :** Jouer intelligemment et dominer les batailles d’escadron.\n"
                "• **Engagement :** Progression constante et top classement SQB."
            ),
            inline=False
        )

        # Bloc 2 : L'ambiance & Le Discord
        embed2.add_field(
            name="🤝 | Notre ADN",
            value=(
                "**Ce que nous privilégions :**\n"
                "• Jeu d’équipe structuré & entraide.\n"
                "• Ambiance vocale active (SQB, training).\n"
                "• Respect et esprit semi-compétitif."
            ),
            inline=False
        )

        # Bloc 3 : Critères de recrutement (Le plus important)
        embed2.add_field(
            name="📋 | Critères & Profil",
            value=(
                "**Prérequis techniques :**\n"
                "• Min. **2 nations RANG V** débloquées (Tank/Avion).\n"
                "• **1300+ points d'activité** dès la première saison.\n\n"
                "**Profil recherché :**\n"
                "• Joueur d'escouade, réactif et respectueux."
            ),
            inline=False
        )

        # Bloc 4 : Conclusion / Contact
        embed2.add_field(
            name="📩 | Prêt à nous rejoindre ?",
            value="Une question ? N'hésite pas à contacter le staff en privé !",
            inline=False
        )

        embed2.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

        return [embed1, embed2]

    def embd_confirmation(self):
        error_page = self.error_page

        if error_page is not None:
            embed = nextcord.Embed(
                title="🧾 ERREUR - FERMETURE CANDIDATURE",
                description="Une erreur est apparut lors de l'ouverture de la candidature !",
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
                title="🧾 Fermeture de la candidature",
                description="Souhaitez-vous continuer dans la fermeture de la candidature ?",
                color=nextcord.Color.dark_blue()
            )

            embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

            return [embed]


    def embd_y_confirmation(self):
        error_page = self.error_page

        if error_page is not None:
            embed = nextcord.Embed(
                title="🧾 ERREUR - FERMETURE CANDIDATURE",
                description="Une erreur est apparut lors de l'ouverture de la candidature !",
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
            title="🧾 Fermeture de la candidature",
            description="La candidature va se fermer et s'enregitrer, veuillez patienter",
            color=nextcord.Color.dark_blue()
        )

        embed.set_footer(text="PYTHON - EMPIRE GALACTIQUE")

        return [embed]
