import os
import nextcord
import asyncio
from nextcord import PermissionOverwrite

from database.db_tickets import TicketsDB
from utils.tickets_log import save_channel_to_json
from database.models.tickets_class import Ticket, TicketGuilds, TicketViewChannels
from utils.threads.threads import create_admin_thread

from dotenv import load_dotenv
load_dotenv()
TICKETS_LOG_CHANNEL_ID = os.getenv('STAFF_SERVER_TICKETS_LOG_CHANNEL_ID')
GUILD_STAFF_SERVER_ID = os.getenv('GUILD_STAFF_SERVER_ID')

GUILD_SQB_SERVER_ID = os.getenv('GUILD_SQB_SERVER_ID')
SQB_STAFF_ID = os.getenv('SQB_SERVER_STAFF_ROLE_ID')
SQB_STAFF_CHANNEL_ID = os.getenv('SQB_SERVER_STAFF_CHANNEL_ID')

GUILD_COMMUNITY_SERVER_ID = os.getenv('COMMUNITY_SERVER_GUILD_ID')
COMMUNITY_STAFF_ID = os.getenv('COMMUNITY_STAFF_ROLE_ID')
COMMUNITY_STAFF_CHANNEL_ID = os.getenv('COMMUNITY_STAFF_CHANNEL_ID')


class OpenApplication(nextcord.ui.Button):

    def __init__(self, db: TicketsDB):
        super().__init__(label="📥 Poser une candidature", style=nextcord.ButtonStyle.green, custom_id="open_application")
        self.db = db

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)

        view = self.view
        guild = interaction.guild
        user = interaction.user
        step_idx = 0

        # Condition 1 : Si la catégorie = APPLICATIONS = existe, alors on la maintient
        cat_results = self.db.get_cat_ticket(interaction.guild_id, get_all=True)
        category = None

        match cat_results:
            case TicketGuilds() as single_config:
                """CAS 1 : Une seule configuration existe déjà (Objet unique)."""
                category = guild.get_channel(single_config.category_id)
                if category:
                    print("[Applications Views]   Ouverture d'un ticket | Catégorie existante trouvée.")
                else:
                    # Si la DB dit qu'elle existe mais que le canal a été supprimé manuellement sur Discord
                    cat_results = None  # On force le passage au cas de création (cas par défaut)

            case list() as cat_list if len(cat_list) > 0:
                """CAS 2 : Plusieurs configurations existent. Il faut tout nettoyer avant de recréer."""
                print(f"[Applications Views] Nettoyage de {len(cat_list)} anciennes catégories...")

                for config in cat_list[:]:  # On itère sur une copie pour pouvoir supprimer sans erreur d'index
                    channel = guild.get_channel(config.category_id)
                    if channel:
                        await channel.delete()
                    self.db.supress_cat_ticket(config)

                # Après le nettoyage, on passe à la création (on laisse tomber vers le cas par défaut via une exception ou en réinitialisant cat_results)
                cat_results = None

            case _:
                """CAS PAR DÉFAUT : Rien n'existe (None ou liste vide). On crée tout."""
                cat_results = None

        # Condition 3 : Si la catégorie Ticket n'existe pas, alors on le crée
        if cat_results is None:
            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),
                guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
            }

            category = await guild.create_category(
                name="= TICKETS =",
                overwrites=overwrites,
                position=0
            )

            data = TicketGuilds(
                guild_id=guild.id,
                category_id=category.id
            )
            self.db.insert_cat_ticket(data)

            print(f"[Applications Views]   Ouverture d'une candidature | Création d'une catégorie {category.name}")



        channel_results = self.db.get_tickets(interaction.guild_id, interaction.user.id, get_all=True)
        needs_creation = True

        match channel_results:
            case Ticket() as single_ticket:
                channel = guild.get_channel(single_ticket.channel_id)
                voice_channel = guild.get_channel(single_ticket.voice_channel_id)

                if channel and single_ticket.is_application:
                    if voice_channel:
                        await voice_channel.delete()

                    await interaction.followup.send(
                        f"Il existe une candidature ouvert à ton nom, je t'invite à t'y rendre {channel.mention}",
                        delete_after=10
                    )

                    print(f"[Applications Views]   Ouverture d'un ticket | "
                          f"Candidature déjà existant dans la base de données")

                    return

            case list() as ticket_list if len(ticket_list) > 0:
                print(f"[Applications Views] Suppression des anciens tickets pour {user.name}...")

                for t in ticket_list:
                    ch = guild.get_channel(t.channel_id)
                    v_ch = guild.get_channel(t.voice_channel_id)

                    if t.is_application:
                        if v_ch:
                            await v_ch.delete()

                        if ch:
                            await ch.delete()

                        self.db.supress_ticket(t)

            case _:
                pass

        if needs_creation:
            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),
                user: PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True,
                                          read_message_history=True),
                guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
            }

            new_channel = await guild.create_text_channel(
                name=f"✉️-candidature-{user.name}",
                overwrites=overwrites,
                category=category
            )

            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),
                user: PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True,
                                          read_message_history=True, speak=True, attach_files=True, connect=True,
                                          use_voice_activation=True),
                guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
            }

            voice_channel = await guild.create_voice_channel(
                name=f"Recrutement | {user.name}",
                overwrites=overwrites,
                category=category
            )

            await create_admin_thread(
                channel=new_channel
            )


            data = Ticket(
                guild_id=guild.id,
                category_id=category.id,
                step=step_idx,
                channel_id=new_channel.id,
                voice_channel_id=voice_channel.id,
                user_id=user.id,
                user_name=user.name,
                application_ticket=1
            )
            self.db.insert_ticket(data)

            # Mise à jour de la vue et envoi du message initial dans le ticket
            view.update_components(interaction, data)

            await new_channel.send(
                embeds=view.embd_response(data),
                view=view
            )

            print(f"[Applications Views]   Ouverture d'une candidature | Création d'une candidature pour l'utilisateur {user.name}")

            await interaction.followup.send(
                f"Ta candidature a été créé : {new_channel.mention}",
                delete_after=15,
                ephemeral=True
            )
            return

# ── BUTTON URL ─────────────────────────────────────────────────────────

class UrlFormularyButton(nextcord.ui.Button):

    def __init__(self):
        super().__init__(label="Apposer la candidature", style=nextcord.ButtonStyle.green,
                         url="https://docs.google.com/forms/d/e/1FAIpQLSe78vzCSrXA4c_t556UmeMJOA-ajl9-h1Lwrc01C7PgOVkmkA/viewform")

    async def callback(self, interaction: nextcord.Interaction):
        user = interaction.user

        print(f"[Applications Views]   Ouverture du lien URL => Par l'utilisateur: {user.name}")

# ── BUTTON CHOICES #1 ────────────────────────────────────────────────

class CloseTicket(nextcord.ui.Button):

    def __init__(self, db: TicketsDB):
        super().__init__(label="Fermer la candidature", style=nextcord.ButtonStyle.red, custom_id="close_ticket")
        self.db = db

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=False)

        user = interaction.user

        if not interaction.user.guild_permissions.administrator:
            print(f"[Applications Views]   Tentative de fermeture d'une candidature | Par l'utilisateur {user.name}")
            await interaction.followup.send(
                "❌ Tu n'as pas la permission d'utiliser ce bouton.",
                ephemeral=True
            )
            return
        view = self.view

        ticket = self.db.get_open_ticket(
            guild_id=interaction.guild.id,
            channel_id=interaction.channel.id
        )

        print(f"CloseButton      :{ticket}\nGuild_id: {interaction.guild.id} | Channel_id: {interaction.channel.id}")

        if ticket is None:
            print(f"[Applications Views]   Erreur lors de la fermeture d'une candidature | Par l'utilisateur {user.name} | "
                  f"Ticket retourne None")
            await interaction.followup.send(
                "❌ Erreur lors de la fermeture de la candidature, la candidature n'existe pas dans la base de données",
                ephemeral=True
            )
            return

        ticket.step = 1

        for item in view.children:
            item.disabled = True

        view.update_components(interaction, ticket)

        print(f"[Applications Views]   Fermeture d'une candidature | Par l'utilisateur {user.name}")

        await interaction.edit_original_message(
            embeds=view.embd_confirmation(),
            view=view
        )


# ── BUTTON CONFIRMATION ────────────────────────────────────────────────

class YesButton(nextcord.ui.Button):

    def __init__(self, db: TicketsDB):
        super().__init__(label="Oui", style=nextcord.ButtonStyle.green, custom_id="yes_ticket_button")
        self.db = db

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)

        view = self.view
        guild = interaction.guild
        user = interaction.user

        ticket = self.db.get_open_ticket(guild_id=guild.id, channel_id=interaction.channel.id)
        print(f"YesButton      :{ticket}\n"
              f"Guild_id: {guild.id} | Channel_id: {interaction.channel.id}")
        if ticket is None:
            print(f"[Applications Views]   Erreur lors de la confirmation de fermeture de la candidature | Par l'utilisateur {user.name} | "
                  f"Ticket retourne None")
            await interaction.followup.send(
                "❌ Erreur lors de la confirmation de fermeture de la candidature, "
                "la Candidature n'existe pas dans la base de données",
                ephemeral=True
            )
            return

        channel = guild.get_channel(ticket.channel_id)
        voice_channel = guild.get_channel(ticket.voice_channel_id)

        await interaction.edit_original_message(
            embeds=view.embd_y_confirmation(),
            view=view
        )

        for item in view.children:
            item.disabled = True

        if not voice_channel:
            print(f"[Applications Views]   Confirmation de fermeture de la candidature => Par l'utilisateur: {user.name}"
                  f" | Channel: ️✉️-candidature-{user.name}")
        else:
            print(f"[Applications Views]   Confirmation de fermeture de la candidature => Par l'utilisateur: {user.name}"
                  f" | Salon textuel: ✉️-candidature-{user.name} | Vocal: Recrutement | {user.name}")

        file_path = await save_channel_to_json(channel)

        guild_staff = interaction.client.get_guild(int(GUILD_STAFF_SERVER_ID))
        log_channel = guild_staff.get_channel(int(TICKETS_LOG_CHANNEL_ID))

        if log_channel and file_path:
            file_to_send = nextcord.File(file_path)
            await log_channel.send(
                content=f"📁 **Archive de la candidature **\nUtilisateur: {ticket.user_name}\n"
                        f"Canal: {channel.name}",
                file=file_to_send
            )

            print(f"[Applications Views]   Archivage automatique de la candidature!")

        if channel:
            await channel.delete()

        if voice_channel:
            await voice_channel.delete()

        self.db.supress_ticket(ticket)

class NoButton(nextcord.ui.Button):

    def __init__(self, db: TicketsDB):
        super().__init__(label="Non", style=nextcord.ButtonStyle.red, custom_id="no_ticket_button")
        self.db = db

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)

        view = self.view
        guild = interaction.guild
        user = interaction.user

        ticket = self.db.get_open_ticket(guild_id=guild.id, channel_id=interaction.channel.id)
        if ticket is None:
            print(
                f"[Applications Views]   Erreur lors de la confirmation de fermeture de la candidature | Par l'utilisateur {user.name} | "
                f"Ticket retourne None")
            await interaction.followup.send(
                "❌ Erreur lors de la confirmation de fermeture de la candidature, la candidature n'existe pas "
                "dans la base de données",
                ephemeral=True
            )
            return

        channel = guild.get_channel(ticket.channel_id)

        ticket.step = 0

        self.db.update_ticket(ticket)

        for item in view.children:
            item.disabled = True

        view.update_components(interaction, ticket)

        print(f"[Applications Views]   Annulation de la fermeture de la candidature => Par l'utilisateur: {user.name}"
              f" | Channel: {channel.name}")

        await interaction.edit_original_message(
            embeds=view.embd_response(ticket),
            view=view
        )