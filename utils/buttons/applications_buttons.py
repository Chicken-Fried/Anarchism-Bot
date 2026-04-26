import os
import nextcord
import asyncio
from nextcord import PermissionOverwrite

from database.db_tickets import TicketsDB
from utils.tickets_log import save_channel_to_json
from database.models.tickets_class import Ticket, TicketGuilds, TicketViewChannels
from embed.tickets_embeds import alert_ticket_embed, AlertTicketEmbed
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

ROLES_ID = {
    int(GUILD_SQB_SERVER_ID): (int(SQB_STAFF_ID), int(SQB_STAFF_CHANNEL_ID)),
    int(GUILD_COMMUNITY_SERVER_ID): (int(COMMUNITY_STAFF_ID), int(COMMUNITY_STAFF_CHANNEL_ID)),
}


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

        if isinstance(cat_results, TicketGuilds):
            category = guild.get_channel(cat_results.category_id)

            if category:
                print(f"[Applications Views]   Ouverture d'un ticket | "
                      f"Catégorie déjà existante dans la base de données")

        # Condition 2 : Si les catégories Applications existent, on va tous les supprimer pour en créer qu'une
        elif isinstance(cat_results, list):
            i = 0
            for cat in cat_results[:]:
                category = guild.get_channel(cat.category_id)
                print(f"[Applications Views]    Category: {category}")
                i += 1
                if category is None:
                    self.db.supress_cat_ticket(cat)
                    cat_results.remove(cat)
                    continue

                await category.delete()
                self.db.supress_cat_ticket(cat)

            print(f"[Applications Views]   Ouverture d'un ticket | "
                  f"Suppression de l'ensemble des catégories ouverte dans la meme guild - Nombre: {i}")

            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),
                user: PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True,
                                          read_message_history=True),
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

            print(f"[Tickets Views]   Ouverture d'un ticket | Création d'une catégorie {category.name}")

        # Condition 3 : Si la catégorie Ticket n'existe pas, alors on le crée
        if cat_results is None or category is None:
            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),
                user: PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True,
                                          read_message_history=True),
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
        channel = None

        # Condition 4 : Si le ticket de l'utilisateur existe, alors on la maintient
        if isinstance(channel_results, Ticket):
            ch = channel_results
            channel = guild.get_channel(ch.channel_id)
            voice_channel = guild.get_channel(ch.voice_channel_id)

            if channel and ch.is_application:
                if voice_channel:
                    await voice_channel.delete()

                await interaction.followup.send(
                    f"Il existe une candidature ouvert à ton nom, je t'invite à t'y rendre {channel.mention}",
                    delete_after=10
                )

                print(f"[Applications Views]   Ouverture d'un ticket | "
                      f"Candidature déjà existant dans la base de données")

                return


        # Condition 5 : Si plusieurs tickets de l'utilisateur existe, alors on supprimer tous et on en crée une seule
        elif isinstance(channel_results, list):
            i = 0
            for ch in channel_results[:]:
                channel = guild.get_channel(ch.channel_id)
                voice_channel = guild.get_channel(ch.voice_channel_id)

                print(f"[Applications Views]    Channel: {channel}")
                i+=1

                if channel is None and ch.is_application:
                    if voice_channel:
                        await voice_channel.delete()

                    self.db.supress_ticket(ch)
                    channel_results.remove(ch)
                    continue
                elif channel and ch.is_application:
                    if voice_channel:
                        await voice_channel.delete()

                    await channel.delete()
                    self.db.supress_ticket(ch)


            print(f"[Applications Views]   Ouverture d'une candidature | "
                  f"Suppression de {i} tickets candidatures de l'utilisateur {user.name}")


            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),
                user: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
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
                user: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
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

            result = ROLES_ID.get(guild.id)

            if result:
                staff_channel_id = result[0]
                alert_channel_id = result[1]

                # 2. Récupération des objets canaux
                ping_ch = guild.get_channel(alert_channel_id)
                ping_staff = guild.get_channel(staff_channel_id)

                if ping_ch and ping_staff:
                    at_embeds = AlertTicketEmbed(
                        title=f"🧾 | Un utilisateur a ouvert une candidature | <#{new_channel.id}> !",
                        description=(
                            f"N'hésitez pas à finaliser sa candidature et à le recruter "
                            f"dès que vous êtes disponible !\n"
                            f"{ping_staff.mention}"
                        ),
                    )

                    await ping_ch.send(
                        embed=alert_ticket_embed(
                            at_embed=at_embeds
                        )
                    )
                else:
                    print(
                        f"[Applications Views]   Ouverture d'une candidature | Erreur dans l'envoie des pings dans le "
                        f"channel staff")


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

            view.update_components(interaction, data)

            await new_channel.send(
                embeds=view.embd_response(data),
                view=view
            )

            print(f"[Applications Views]   Ouverture d'un ticket | Création d'un ticket pour l'utilisateur {user.name}")

            await interaction.followup.send(
                f"Ta candidature a été créé : {new_channel.mention}",
                delete_after=15,
                ephemeral=True
            )
            return

        # Condition 5 : Si aucun ticket ouvert, on en crée un
        if channel_results is None or channel is None:
            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),
                user: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                          read_message_history=True),
                guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
            }

            new_channel = await guild.create_text_channel(
                name=f"️️✉️️-candidature-{user.name}",
                overwrites=overwrites,
                category=category
            )

            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),
                user: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
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

            result = ROLES_ID.get(guild.id)

            if result:
                staff_channel_id = result[0]
                alert_channel_id = result[1]

                # 2. Récupération des objets canaux
                ping_ch = guild.get_channel(alert_channel_id)
                ping_staff = guild.get_channel(staff_channel_id)

                if ping_ch and ping_staff:
                    at_embeds = AlertTicketEmbed(
                        title=f"🧾 | Un utilisateur a ouvert une candidature | <#{new_channel.id}> !",
                        description=(
                            f"N'hésitez pas à finaliser sa candidature et à le recruter "
                            f"dès que vous êtes disponible !\n"
                            f"{ping_staff.mention}"
                        ),
                    )

                    await ping_ch.send(
                        embed=alert_ticket_embed(
                            at_embed=at_embeds
                        )
                    )
                else:
                    print(
                        f"[Applications Views]   Ouverture d'une candidature | Erreur dans l'envoie des pings dans le "
                        f"channel staff")


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

            view.update_components(interaction, data)

            await new_channel.send(
                embeds=view.embd_response(data),
                view=view
            )

            print(f"[Applications Views]   Ouverture d'une candidature | Création d'une candidature pour l'utilisateur "
                  f"{user.name}")

            await interaction.followup.send(
                f"Ta candidature a été créé : {new_channel.mention}",
                ephemeral=True,
                delete_after=15
            )

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
        super().__init__(label="Fermer la candidature", style=nextcord.ButtonStyle.grey, custom_id="close_ticket")
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