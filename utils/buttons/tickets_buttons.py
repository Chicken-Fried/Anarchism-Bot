import os
import nextcord
import asyncio
from nextcord import PermissionOverwrite

from database.db_tickets import TicketsDB
from utils.tickets_log import save_channel_to_json
from utils.inputs.tickets_inputs import AbsentModal
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


# ── BUTTON OPEN TICKET ───────────────────────────────────────────────

class OpenTicket(nextcord.ui.Button):

    def __init__(self, db: TicketsDB):
        super().__init__(label="Ouvrir un ticket", style=nextcord.ButtonStyle.green, custom_id="open_ticket")
        self.db = db

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)

        view = self.view
        guild = interaction.guild
        user = interaction.user
        step_idx = 0

        # Condition 1 : Si la catégorie = TICKETS = existe, alors on la maintient
        cat_results = self.db.get_cat_ticket(interaction.guild_id, get_all=True)

        print(f"CAT RESULTS:    {cat_results}")
        category = None

        if isinstance(cat_results, TicketGuilds):
            category = guild.get_channel(cat_results.category_id)

            if category:
                print(f"[Tickets Views]   Ouverture d'un ticket | "
                      f"Catégorie déjà existante dans la base de données")

        # Condition 2 : Si les catégories Ticket existent, on va tous les supprimer pour en créer qu'une
        elif isinstance(cat_results, list):
            i = 0
            for cat in cat_results[:]:
                category = guild.get_channel(cat.category_id)
                i += 1
                if category is None:
                    self.db.supress_cat_ticket(cat)
                    cat_results.remove(cat)
                    continue

                await category.delete()
                self.db.supress_cat_ticket(cat)

            print(f"[Tickets Views]   Ouverture d'un ticket | "
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

            print(f"[Tickets Views]   Ouverture d'un ticket | Création d'une catégorie {category.name}")



        channel_results = self.db.get_tickets(interaction.guild_id, interaction.user.id, get_all=True)
        channel = None

        # Condition 4 : Si le ticket de l'utilisateur existe, alors on la maintient
        if isinstance(channel_results, Ticket):
            channel = guild.get_channel(channel_results.channel_id)

            if channel and not channel_results.is_application:
                await interaction.followup.send(
                    f"Il existe un ticket ouvert à ton nom, je t'invite à t'y rendre {channel.mention}",
                    delete_after=10
                )

                print(f"[Tickets Views]   Ouverture d'un ticket | "
                      f"Ticket déjà existant dans la base de données")


        # Condition 5 : Si plusieurs tickets de l'utilisateur existe, alors on supprimer tous et on en crée une seule
        elif isinstance(channel_results, list):
            i = 0
            for ch in channel_results[:]:
                channel = guild.get_channel(ch.channel_id)
                print(f"[Tickets Views]    Channel: {channel}")
                i+=1

                if channel is None and not ch.is_application:
                    self.db.supress_ticket(ch)
                    channel_results.remove(ch)
                    continue
                elif channel and not ch.is_application:
                    await channel.delete()
                    self.db.supress_ticket(ch)


            print(f"[Tickets Views]   Ouverture d'un ticket | "
                  f"Suppression de {i} tickets de l'utilisateur {user.name}")

            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),
                user: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                          read_message_history=True),
                guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
            }

            new_channel = await guild.create_text_channel(
                name=f"🐍-ticket-{user.name}",
                overwrites=overwrites,
                category=category
            )

            await create_admin_thread(
                channel=new_channel
            )

            result = ROLES_ID.get(guild.id)

            if result:
                staff_id = result[0]
                alert_channel_id = result[1]

                # 2. Récupération des objets canaux
                ping_ch = guild.get_channel(alert_channel_id)
                ping_staff = guild.get_role(staff_id)

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
                        f"[Tickets Views]   Ouverture d'une candidature | Erreur dans l'envoie des pings dans le "
                        f"channel staff")

            data = Ticket(
                guild_id=guild.id,
                category_id=category.id,
                step=step_idx,
                channel_id=new_channel.id,
                user_id=user.id,
                user_name=user.name,
                application_ticket=0
            )
            self.db.insert_ticket(data)

            view.update_components(interaction, data)

            await new_channel.send(
                embeds=view.embd_choice_reason(),
                view=view
            )

            print(f"[Tickets Views]   Ouverture d'un ticket | Création d'un ticket pour l'utilisateur {user.name}")

            await interaction.followup.send(
                f"Ton ticket a été créé : {new_channel.mention}",
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
                name=f"🐍-ticket-{user.name}",
                overwrites=overwrites,
                category=category
            )

            result = ROLES_ID.get(guild.id)

            if result:
                staff_id = result[0]
                alert_channel_id = result[1]

                # 2. Récupération des objets canaux
                ping_ch = guild.get_channel(alert_channel_id)
                ping_staff = guild.get_role(staff_id)

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
                        f"[Tickets Views]   Ouverture d'une candidature | Erreur dans l'envoie des pings dans le "
                        f"channel staff")

            data = Ticket(
                guild_id=guild.id,
                category_id=category.id,
                step=step_idx,
                channel_id=new_channel.id,
                user_id=user.id,
                user_name=user.name,
                application_ticket=0
            )
            self.db.insert_ticket(data)

            view.update_components(interaction, data)

            await new_channel.send(
                embeds=view.embd_choice_reason(),
                view=view
            )

            await create_admin_thread(
                channel=new_channel
            )

            print(f"[Tickets Views]   Ouverture d'un ticket | Création d'un ticket' pour l'utilisateur {user.name}")

            await interaction.followup.send(
                f"Ton ticket a été créé : {new_channel.mention}",
                delete_after=15,
                ephemeral=True
            )



# ── BUTTON CHOICES #1 ────────────────────────────────────────────────

class CloseTicket(nextcord.ui.Button):

    def __init__(self, db: TicketsDB):
        super().__init__(label="Fermer le ticket", style=nextcord.ButtonStyle.grey, custom_id="close_ticket")
        self.db = db

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=False)

        user = interaction.user

        if not interaction.user.guild_permissions.administrator:
            print(f"[Tickets Views]   Tentative de fermeture d'un ticket | Par l'utilisateur {user.name}")
            await interaction.followup.send(
                "❌ Tu n'as pas la permission d'utiliser ce bouton.",
                ephemeral=True
            )
            return

        view = self.view

        ticket = self.db.get_open_ticket(
            guild_id=interaction.guild.id, channel_id=interaction.channel.id)

        print(f"CloseButton      :{ticket}\nGuild_id: {interaction.guild.id} | Channel_id: {interaction.channel.id}")

        if ticket is None:
            print(f"[Tickets Views]   Erreur lors de la fermeture d'un ticket | Par l'utilisateur {user.name} | "
                  f"Ticket retourne None")
            await interaction.followup.send(
                "❌ Erreur lors de la fermeture du ticket, le Ticket n'existe pas dans la base de données",
                ephemeral=True
            )
            return

        ticket.step = 2

        for item in view.children:
            item.disabled = True

        view.update_components(interaction, ticket)

        print(f"[Tickets Views]   Fermeture d'un ticket | Par l'utilisateur {user.name}")

        #self.db.supress_ticket(ticket)

        await interaction.edit_original_message(
            embeds=view.embd_confirmation(),
            view=view
        )

class BackTicket(nextcord.ui.Button):

    def __init__(self, db: TicketsDB):
        super().__init__(label="Retour en arrière", style=nextcord.ButtonStyle.blurple, custom_id="step_back_ticket")
        self.db = db

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=False)

        view = self.view
        guild = interaction.guild
        user = interaction.user

        ticket = self.db.get_open_ticket(guild_id=guild.id, channel_id=interaction.channel.id)
        if ticket is None:
            print(f"[Tickets Views]   Erreur lors du retour vers le menu des choix | Par l'utilisateur {user.name} | "
                  f"Ticket retourne None")
            await interaction.followup.send(
                "❌ Erreur lors du retour vers le menu des choix, le Ticket n'existe pas dans la base de données"
            )
            return

        channel = guild.get_channel(ticket.channel_id)
        voice_channel = guild.get_channel(ticket.voice_channel_id)

        if ticket.step > 0:
            ticket.step -= 1
            self.db.update_ticket(ticket)

            for item in view.children:
                item.disabled = True

                # On met à jour la vue pour l'étape précédente
            view.update_components(interaction, ticket)

            await interaction.followup.send(embeds=view.embd_choice_reason(), view=view)
            print(f"[Tickets Views]   Retour à l'étape {ticket.step} | Par {user.name}")

        if ticket.step == 0:
            self.db.update_ticket(ticket)
            view.update_components(interaction, ticket)

            overwrite = PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                            read_message_history=True, attach_files=False)

            await channel.set_permissions(user, overwrite=overwrite)

            print(f"[Tickets Views]   Retour au menu des choix | Par l'utilisateur {user.name}")

            file_path = await save_channel_to_json(channel)

            # 2. Log vers le serveur Staff (Sécurisé)
            try:
                guild_staff = interaction.client.get_guild(int(GUILD_STAFF_SERVER_ID))
                if guild_staff:
                    log_channel = guild_staff.get_channel(int(TICKETS_LOG_CHANNEL_ID))
                    if log_channel and file_path:
                        file_to_send = nextcord.File(file_path)
                        await log_channel.send(
                            content=f"📁 **Archive du ticket**\nUtilisateur: {ticket.user_name}\nCanal: {channel.name}",
                            file=file_to_send
                        )
            except Exception as e:
                print(f"[Error] Erreur lors de l'envoi des logs : {e}")

            new_channel = await channel.clone()

            await interaction.followup.send(f"⚠️ Attention : Le retour à l'étape 0 va réinitialiser "
                                            f"le ticket et archiver la discussion !\n"
                                            f"Pour poursuivre, rendez vous à votre nouveau ticket <#{new_channel.id}>",
                                            ephemeral=True)

            await asyncio.sleep(25)

            await channel.delete()

            await new_channel.send(
                embeds=view.embd_choice_reason(),
                view=view
            )

            await create_admin_thread(
                channel=new_channel
            )

            result = ROLES_ID.get(guild.id)

            if result:
                ping_ch = guild.get_channel(result[1])
                ping_staff = guild.get_channel(result[0])

                if ping_ch and ping_staff:
                    at_embeds = AlertTicketEmbed(
                        title=f"🧾 | Un ticket a été réinitialisé | <@{new_channel.id}> !",
                        description=f"L'utilisateur a fait un retour en arrière.\n<@{ping_staff}>",
                    )
                    await ping_ch.send(embed=alert_ticket_embed(at_embed=at_embeds))

            if voice_channel:
                try:
                    await voice_channel.delete()
                except:
                    pass

            self.db.supress_ticket(ticket)

            new_ticket = Ticket(
                channel_id=new_channel.id,
                guild_id=guild.id,
                user_id=user.id,
                user_name=user.name,
                step=0
            )
            self.db.insert_ticket(new_ticket)

            return

        else:
            self.db.update_ticket(ticket)
            view.error_page[user.id] = 1

            print(f"[Tickets Views]   ERREUR | Retour au menu des choix | Par l'utilisateur {user.name}")

            await interaction.followup.send(
                embeds=view.embd_choice_reason(),
                view=view
            )


class CancelTicket(nextcord.ui.Button):

    def __init__(self, db: TicketsDB):
        super().__init__(label="Annuler", style=nextcord.ButtonStyle.red, custom_id="cancel_ticket")
        self.db = db

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=False)

        view = self.view
        guild = interaction.guild
        user = interaction.user

        ticket = self.db.get_open_ticket(guild_id=guild.id, channel_id=interaction.channel.id)
        if ticket is None:
            print(f"[Tickets Views]   Erreur lors de l'annulation du ticket | Par l'utilisateur {user.name} | "
                  f"Ticket retourne None")
            await interaction.followup.send(
                "❌ Erreur lors de l'annulation du ticket, le Ticket n'existe pas dans la base de données",
                ephemeral=True
            )
            return

        channel = guild.get_channel(ticket.channel_id)
        voice_channel = guild.get_channel(ticket.voice_channel_id)

        for item in view.children:
            item.disabled = True

        ticket.step = 3
        view.update_components(interaction, ticket)
        ticket.step = 0

        self.db.update_ticket(ticket)

        print(f"[Tickets Views]   Annulation du ticket | 🐍-ticket-{user.name} | Par l'utilisateur {user.name}")

        async for message in channel.history(limit=100):
            if message.author == interaction.user:
                await interaction.followup.send(
                    "Cela implique la suppresion de l'ensemble de la discussion du ticket !",
                    ephemeral=True
                )

                file_path = await save_channel_to_json(channel)

                guild_staff = interaction.client.get_guild(int(GUILD_STAFF_SERVER_ID))
                log_channel = guild_staff.get_channel(int(TICKETS_LOG_CHANNEL_ID))

                if log_channel and file_path:
                    file_to_send = nextcord.File(file_path)
                    await log_channel.send(
                        content=f"📁 **Archive du ticket **\nUtilisateur: {ticket.user_name}\n"
                                f"Canal: {channel.name}",
                        file=file_to_send
                    )

                    print(f"[Tickets Views]   Archivage automatique du ticket!")

                await asyncio.sleep(10)

                new_channel = await channel.clone()
                await channel.delete()

                await new_channel.send(
                    embeds=view.embd_choice_reason(),
                    view=view
                )

                await create_admin_thread(
                    channel=new_channel
                )

                result = ROLES_ID.get(guild.id)

                if result:
                    ping_ch = guild.get_channel(result[1])
                    ping_staff = guild.get_channel(result[0])

                    at_embeds = AlertTicketEmbed(
                        title=f"🧾 | Un utilisateur à re-ouvert un ticket | <@{new_channel.id}> !",
                        description=f"Hésitez pas à aider l'utilisateur le plus vite possible !\n"
                                    f"<@{ping_staff}>",
                    )

                    await ping_ch.send(
                        embed=alert_ticket_embed(
                            at_embed=at_embeds
                        )
                    )

                if voice_channel:
                    await voice_channel.delete()

                self.db.supress_ticket(ticket)

                new_ticket = Ticket(
                    channel_id=new_channel.id,
                    guild_id=guild.id,
                    user_id=user.id,
                    user_name=user.name,
                    step=0
                )
                self.db.insert_ticket(new_ticket)

                return

        file_path = await save_channel_to_json(channel)

        guild_staff = interaction.client.get_guild(int(GUILD_STAFF_SERVER_ID))
        log_channel = guild_staff.get_channel(int(TICKETS_LOG_CHANNEL_ID))

        if log_channel and file_path:
            file_to_send = nextcord.File(file_path)
            await log_channel.send(
                content=f"📁 **Archive du ticket supprimé**\nUtilisateur: {ticket.user_name}\n"
                        f"Canal: {channel.name}",
                file=file_to_send
            )

            print(f"[Tickets Views]   Archivage automatique du ticket!")

        await interaction.followup.send(
            embeds=view.embd_cancel_ticket(),
            view=view,
            delete_after=10
        )

        await asyncio.sleep(10)

        new_channel = await channel.clone()
        await channel.delete()

        if voice_channel:
            await voice_channel.delete()

        await new_channel.send(
            embeds=view.embd_choice_reason(),
            view=view
        )

        await create_admin_thread(
            channel=new_channel
        )

        result = ROLES_ID.get(guild.id)

        if result:
            ping_ch = guild.get_channel(result[1])
            ping_staff = guild.get_channel(result[0])

            at_embeds = AlertTicketEmbed(
                title=f"🧾 | Un utilisateur à re-ouvert un ticket | <@{new_channel.id}> !",
                description=f"Hésitez pas à aider l'utilisateur le plus vite possible !\n"
                            f"<@{ping_staff}>",
            )

            await ping_ch.send(
                embed=alert_ticket_embed(
                    at_embed=at_embeds
                )
            )

        self.db.supress_ticket(ticket)

        new_ticket = Ticket(
            channel_id=new_channel.id,
            guild_id=guild.id,
            user_id=user.id,
            user_name=user.name,
            step=0
        )
        self.db.insert_ticket(new_ticket)


# ── BUTTON CHOICES #2 ────────────────────────────────────────────────

class SuggestTicket(nextcord.ui.Button):

    def __init__(self, db: TicketsDB):
        super().__init__(label="Introduire une suggestion", style=nextcord.ButtonStyle.grey, custom_id="suggest_button")
        self.db = db

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=False)

        view = self.view
        guild = interaction.guild
        user = interaction.user

        ticket = self.db.get_open_ticket(guild_id=guild.id, channel_id=interaction.channel.id)
        if ticket is None:
            print(f"[Tickets Views]   Erreur lors du choix effectué => Suggestion | Par l'utilisateur {user.name} | "
                  f"Ticket retourne None")
            await interaction.followup.send(
                "❌ Erreur lors du choix effectué => Suggestion, le Ticket n'existe pas dans la base de données",
                ephemeral=True
            )
            return

        channel = guild.get_channel(ticket.channel_id)

        for item in view.children:
            item.disabled = True

        ticket.step = 1
        ticket.reason_ticket = 0
        self.db.update_ticket(ticket)

        for item in view.children:
            item.disabled = True

        view.update_components(interaction, ticket)

        print(f"[Tickets Views]   Choix effectué => Suggestion | Utilisateur: {user.name}")

        overwrite = PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True,
                                        read_message_history=True, attach_files=True)

        await channel.set_permissions(user, overwrite=overwrite)

        await interaction.edit_original_message(
            embeds=view.embd_response_reason(ticket),
            view=view
        )

class IssuesTicket(nextcord.ui.Button):

    def __init__(self, db: TicketsDB):
        super().__init__(label="Faire part d'un problème", style=nextcord.ButtonStyle.grey, custom_id="issue_button")
        self.db = db

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=False)

        view = self.view
        guild = interaction.guild
        user = interaction.user

        ticket = self.db.get_open_ticket(guild_id=guild.id, channel_id=interaction.channel.id)
        if ticket is None:
            print(f"[Tickets Views]   Erreur lors du choix effectué => Problème | Par l'utilisateur {user.name} | "
                  f"Ticket retourne None")
            await interaction.followup.send(
                "❌ Erreur lors du choix effectué => Problème, le Ticket n'existe pas dans la base de données",
                ephemeral=True
            )
            return

        channel = guild.get_channel(ticket.channel_id)

        ticket.step = 1
        ticket.reason_ticket = 1
        view.update_components(interaction, ticket)

        self.db.update_ticket(ticket)

        for item in view.children:
            item.disabled = True

        view.update_components(interaction, ticket)

        print(f"[Tickets Views]   Choix effectué => Problème | Utilisateur: {user.name}")

        overwrite = PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True,
                                        read_message_history=True, attach_files=True)

        await channel.set_permissions(user, overwrite=overwrite)

        #ticket.reason_ticket = 1
        #self.db.update_ticket(ticket)

        await interaction.edit_original_message(
            embeds=view.embd_response_reason(ticket),
            view=view
        )


class AbsentTicket(nextcord.ui.Button):
    def __init__(self, db: TicketsDB):
        super().__init__(label="Introduire une absence", style=nextcord.ButtonStyle.grey, custom_id="absent_button")
        self.db = db

    async def callback(self, interaction: nextcord.Interaction):
        view = self.view
        guild = interaction.guild
        user = interaction.user

        ticket = self.db.get_open_ticket(guild_id=guild.id, channel_id=interaction.channel.id)
        if ticket is None:
            print(f"[Tickets Views]   Erreur lors du choix effectué => Absence | Par l'utilisateur {user.name} | "
                  f"Ticket retourne None")
            await interaction.response.send_message(
                "❌ Erreur lors du choix effectué => Absence, le Ticket n'existe pas dans la base de données",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(AbsentModal(db=self.db))

        channel = guild.get_channel(ticket.channel_id)

        for item in view.children:
            item.disabled = True

        ticket.step = 1
        self.db.update_ticket(ticket)

        view.update_components(interaction, ticket)

        print(f"[Tickets Views]   Choix effectué => Absence | Utilisateur: {user.name}")

        """overwrite = PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True,
                                        read_message_history=True, attach_files=True)

        await channel.set_permissions(user, overwrite=overwrite)"""

        ticket.reason_ticket = 2
        self.db.update_ticket(ticket)

        await interaction.edit_original_message(
            embeds=view.embd_response_reason(ticket),
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
            print(f"[Tickets Views]   Erreur lors de la confirmation de fermeture du ticket | Par l'utilisateur {user.name} | "
                  f"Ticket retourne None")
            await interaction.followup.send(
                "❌ Erreur lors de la confirmation de fermeture du ticket, le Ticket n'existe pas dans la base de données",
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
            print(f"[Tickets Views]   Confirmation de fermeture du ticket => Par l'utilisateur: {user.name}"
                  f" | Channel: 🐍-ticket-{user.name}")
        else:
            print(f"[Tickets Views]   Confirmation de fermeture du ticket => Par l'utilisateur: {user.name}"
                  f" | Salon textuel: 🐍-ticket-{user.name} | Vocal: Recrutement | {user.name}")

        file_path = await save_channel_to_json(channel)

        try:
            guild_staff = interaction.client.get_guild(int(GUILD_STAFF_SERVER_ID))
            if guild_staff:
                log_channel = guild_staff.get_channel(int(TICKETS_LOG_CHANNEL_ID))
                if log_channel and file_path:
                    file_to_send = nextcord.File(file_path)
                    await log_channel.send(
                        content=f"📁 **Archive du ticket**\nUtilisateur: {ticket.user_name}\nCanal: {channel.name}",
                        file=file_to_send
                    )
        except Exception as e:
            print(f"[Error] Erreur lors de l'envoi des logs : {e}")

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
                f"[Tickets Views]   Erreur lors de la confirmation de fermeture du ticket | Par l'utilisateur {user.name} | "
                f"Ticket retourne None")
            await interaction.response.send_message(
                "❌ Erreur lors de la confirmation de fermeture du ticket, le Ticket n'existe pas dans la base de données",
                ephemeral=True
            )
            return

        channel = guild.get_channel(ticket.channel_id)

        for item in view.children:
            item.disabled = True

        ticket.step = 2

        self.db.update_ticket(ticket)

        for item in view.children:
            item.disabled = True

        view.update_components(interaction, ticket)

        print(f"[Tickets Views]   Annulation de la fermeture du ticket => Par l'utilisateur: {user.name}"
              f" | Channel: {channel.name}")

        await interaction.edit_original_message(
            embeds=view.embd_response_reason(ticket),
            view=view
        )