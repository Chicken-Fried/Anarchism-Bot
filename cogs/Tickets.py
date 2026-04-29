import os
from unittest import case

import nextcord
import asyncio
from nextcord.ext import commands
from nextcord import PermissionOverwrite

from views.tickets_views import OpenTicketsView
from views.applications_views import OpenApplicationsView
from utils.tickets_log import save_channel_to_json
from database.models.tickets_class import Ticket, TicketViewChannels, TicketGuilds
from utils.threads.threads import create_admin_thread

# ── PARAMETRES INITIALS ────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv()
TICKETS_LOG_CHANNEL_ID = os.getenv('STAFF_SERVER_TICKETS_LOG_CHANNEL_ID')
GUILD_STAFF_SERVER_ID = os.getenv('GUILD_STAFF_SERVER_ID')

COMMUNITY_GUILD_ID = os.getenv('COMMUNITY_SERVER_GUILD_ID')


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db_tickets

    @commands.Cog.listener()
    async def on_ready(self):
        print("[Tickets Cog]   Le Cog est prêt!")

    """@nextcord.slash_command(
        name="make-channel_ticket-channel",
        description="Transforme ce channel en créateur de ticket",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def update_channel_to_channel_ticket(self, interaction: nextcord.Interaction):
        view = OpenTicketsView(db=self.db)
        data = TicketViewChannels(
            guild_id=interaction.guild.id,
            view_channel_id=interaction.channel.id
        )
        self.db.insert_ch_ticket(data)

        await interaction.response.send_message(
            embeds=view.embd_open_ticket(),
            view=view,
            ephemeral=False
        )"""

    @nextcord.slash_command(
        name="add-application-channel",
        description="Ajoute le channel dédié aux candidatures",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def create_channel_application(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        view = OpenApplicationsView(db=self.db)

        results = self.db.get_ch_application(guild.id, get_all=True)

        if isinstance(results, TicketViewChannels):
            channel = guild.get_channel(results.view_channel_id)
            if channel:
                await interaction.followup.send(
                    content=f"❌ - Un channel application viewer existe déjà, le voici => {channel.mention}",
                    ephemeral=True
                )
            else:
                if results:
                    self.db.supress_ch_application(results)
                await interaction.followup.send(
                    content=f"✅ - Suppression du channel dans la base de données\n"
                            f"✅ - Création d'un nouveau channel application viewer\n"
                            f"Si il existe vous pouvez le supprimer en toute sureté !",
                    ephemeral=True
                )

                overwrites = {
                    guild.default_role: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                                            read_message_history=True),
                    guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
                }

                channel = await interaction.guild.create_text_channel(
                    name=f"📋-candidature",
                    overwrites=overwrites,
                    position=0
                )

                data = TicketViewChannels(
                    guild_id=interaction.guild.id,
                    view_channel_id=channel.id
                )
                self.db.insert_ch_application(data)

                await channel.send(
                    embeds=view.embd_open_ticket(),
                    view=view
                )
                return

        if isinstance(results, list):
            for result in results:
                channel = guild.get_channel(results.view_channel_id)
                if channel:
                    await channel.delete()
                    self.db.supress_ch_application(result)
                else:
                    if result:
                        self.db.supress_ch_application(result)

            await interaction.followup.send(
                content=f"✅ - Suppression des applications viewer dans la base de données\n"
                        f"✅ - Création d'un nouveau channel application viewer",
                ephemeral=True
            )

            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                                        read_message_history=True),
                guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
            }

            channel = await interaction.guild.create_text_channel(
                name=f"📋-candidature",
                overwrites=overwrites,
                position=0
            )

            data = TicketViewChannels(
                guild_id=interaction.guild.id,
                view_channel_id=channel.id
            )
            self.db.insert_ch_application(data)

            await channel.send(
                embeds=view.embd_open_application(),
                view=view
            )
            return

        await interaction.followup.send(
            content=f"✅ - Aucun application viewer dans la base de données\n"
                    f"✅ - Création d'un nouveau channel application viewer",
            ephemeral=True
        )

        overwrites = {
            guild.default_role: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                                    read_message_history=True),
            guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
        }

        channel = await interaction.guild.create_text_channel(
            name=f"📋-candidature",
            overwrites=overwrites,
            position=0
        )

        data = TicketViewChannels(
            guild_id=interaction.guild.id,
            view_channel_id=channel.id
        )
        self.db.insert_ch_application(data)

        await channel.send(
            embeds=view.embd_open_application(),
            view=view
        )
        return

    @nextcord.slash_command(
        name="add-ticket-channel",
        description="Ajoute le channel dédié aux tickets",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def create_channel_ticket(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        view = OpenTicketsView(db=self.db)

        results = self.db.get_ch_ticket(guild.id, get_all=True)

        if isinstance(results, TicketViewChannels):
            channel = guild.get_channel(results.view_channel_id)
            if channel:
                await interaction.followup.send(
                    content=f"❌ - Un channel ticket viewer existe déjà, le voici => {channel.mention}",
                    ephemeral=True
                )
            else:
                if results:
                    self.db.supress_ch_ticket(results)
                await interaction.followup.send(
                    content=f"✅ - Suppression du channel dans la base de données\n"
                        f"✅ - Création d'un nouveau channel ticket viewer\n"
                        f"Si il existe vous pouvez le supprimer en toute sureté !",
                    ephemeral=True
                )

                overwrites = {
                    guild.default_role: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                              read_message_history=True),
                    guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
                }

                channel = await interaction.guild.create_text_channel(
                    name=f"📥-ouvrir-un-ticket",
                    overwrites=overwrites,
                    position=0
                )

                data = TicketViewChannels(
                    guild_id=interaction.guild.id,
                    view_channel_id=channel.id
                )
                self.db.insert_ch_ticket(data)

                await channel.send(
                    embeds=view.embd_open_ticket(),
                    view=view
                )
                return

        if isinstance(results, list):
            for result in results:
                channel = guild.get_channel(results.view_channel_id)
                if channel:
                    await channel.delete()
                    self.db.supress_ch_ticket(result)
                else:
                    if result:
                        self.db.supress_ch_ticket(result)

            await interaction.followup.send(
                content=f"✅ - Suppression des ticket viewer dans la base de données\n"
                    f"✅ - Création d'un nouveau channel ticket viewer",
                ephemeral=True
            )

            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                                        read_message_history=True),
                guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
            }

            channel = await interaction.guild.create_text_channel(
                name=f"📥-ouvrir-un-ticket",
                overwrites=overwrites,
                position=0
            )

            data = TicketViewChannels(
                guild_id=interaction.guild.id,
                view_channel_id=channel.id
            )
            self.db.insert_ch_ticket(data)

            await channel.send(
                embeds=view.embd_open_ticket(),
                view=view
            )
            return

        await interaction.followup.send(
            content=f"✅ - Aucun ticket viewer dans la base de données\n"
                f"✅ - Création d'un nouveau channel ticket viewer",
            ephemeral=True
        )

        overwrites = {
            guild.default_role: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                                    read_message_history=True),
            guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
        }

        channel = await interaction.guild.create_text_channel(
            name=f"📥-ouvrir-un-ticket",
            overwrites=overwrites,
            position=0
        )

        data = TicketViewChannels(
            guild_id=interaction.guild.id,
            view_channel_id=channel.id
        )
        self.db.insert_ch_ticket(data)

        await channel.send(
            embeds=view.embd_open_ticket(),
            view=view
        )
        return


    @nextcord.slash_command(
        name="close-viewer-ticket",
        description="Ferme le salon textuel où se trouve l'afficheur d'ouverture de ticket",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def close_channel_ticket(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        results = self.db.get_ch_ticket(guild.id, get_all=True)

        if isinstance(results, TicketViewChannels):
            channel = guild.get_channel(results.view_channel_id)
            if channel:
                self.db.supress_ch_ticket(results)
                await interaction.followup.send(
                    content=f"✅ - Suppression du channel dans le serveur et dans la base de données",
                    ephemeral=True
                )

                await asyncio.sleep(10)

                await channel.delete()
                return
            else:
                if results:
                    self.db.supress_ch_ticket(results)
                await interaction.followup.send(
                    content=f"✅ - Suppression du channel dans la base de données\n"
                        f"❌ - Aucun channel avec le Viewer Ticket a été trouver dans le serveur\n"
                        f"Si il existe vous pouvez le supprimer en toute sureté !",
                    ephemeral=True
                )
                return

        if isinstance(results, list):
            for result in results:
                channel = guild.get_channel(result.view_channel_id)
                if channel:
                    await channel.delete()
                    self.db.supress_ch_ticket(result)
                else:
                    if result:
                        self.db.supress_ch_ticket(result)
            return

        await interaction.followup.send(
            content=f"❌ - Aucun channel a été trouver dans la base de données\n"
                f"❌ - Aucun channel avec le Viewer Ticket a été trouver dans le serveur\n"
                f"Si il existe vous pouvez le supprimer en toute sureté !",
            ephemeral=True
        )

    @nextcord.slash_command(
        name="close-viewer-application",
        description="Ferme le salon textuel où se trouve l'afficheur d'ouverture de candidature",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def close_channel_application(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        results = self.db.get_ch_application(guild.id, get_all=True)

        if isinstance(results, TicketViewChannels):
            channel = guild.get_channel(results.view_channel_id)
            if channel:
                self.db.supress_ch_application(results)
                await interaction.followup.send(
                    content=f"✅ - Suppression du channel dans le serveur et dans la base de données",
                    ephemeral=True
                )

                await asyncio.sleep(10)

                await channel.delete()
                return
            else:
                if results:
                    self.db.supress_ch_application(results)
                await interaction.followup.send(
                    content=f"✅ - Suppression du channel dans la base de données\n"
                            f"❌ - Aucun channel avec le Viewer Application a été trouver dans le serveur\n"
                            f"Si il existe vous pouvez le supprimer en toute sureté !",
                    ephemeral=True
                )
                return

        if isinstance(results, list):
            for result in results:
                channel = guild.get_channel(result.view_channel_id)
                if channel:
                    await channel.delete()
                    self.db.supress_ch_application(result)
                else:
                    if result:
                        self.db.supress_ch_application(result)
            return

        await interaction.followup.send(
            content=f"❌ - Aucun channel a été trouver dans la base de données\n"
                    f"❌ - Aucun channel avec le Viewer Application a été trouver dans le serveur\n"
                    f"Si il existe vous pouvez le supprimer en toute sureté !",
            ephemeral=True
        )

    @nextcord.slash_command(
        name="open-ticket-for-user",
        description="Ouvre le ticket ou la candidature d'un utilisateur",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def open_user_ticket(
            self,
            interaction: nextcord.Interaction,
            member: nextcord.Member,
            type_ticket: str = nextcord.SlashOption(
                name="type_ticket",
                required=True,
                description="Choisissez le type de ticket",
                choices={
                    "Ticket": "t",
                    "Candidature": "c"
                }
            )
    ):
        await interaction.response.defer(ephemeral=True)

        step_idx = 0
        guild = interaction.guild

        result = self.db.get_tickets(guild.id, member.id)

        category = None

        ticketview = OpenTicketsView(db=self.db)
        applicationview = OpenApplicationsView(db=self.db)

        views = {
            't': (ticketview, "🐍-ticket-"),  # La vue et le préfixe
            'c': (applicationview, "✉️-candidature-")
        }

        cat_results = self.db.get_cat_ticket(
            guild_id=interaction.guild.id,
        )

        match cat_results:
            case TicketGuilds():
                category = guild.get_channel(cat_results.category_id)

                if category:
                    print(f"[Tickets Cogs]   Ouverture d'un ticket | "
                          f"Catégorie déjà existante dans la base de données")
            case list() as cat_list if len(cat_list) > 0:
                print(f"[Tickets Cogs]   Nettoyage de {len(cat_list)} anciennes catégories...")

                for config in cat_list[:]:  # On itère sur une copie pour pouvoir supprimer sans erreur d'index
                    channel = guild.get_channel(config.category_id)
                    if channel:
                        await channel.delete()
                    self.db.supress_cat_ticket(config)

                # Après le nettoyage, on passe à la création (on laisse tomber vers le cas par défaut via une exception ou en réinitialisant cat_results)
            case _:
                pass

        if category is None:
            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),
                guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
            }

            category = await guild.create_category(
                name="= TICKETS =",
                overwrites=overwrites,
                position=0
            )

            new_data = TicketGuilds(
                guild_id=guild.id,
                category_id=category.id
            )
            self.db.insert_cat_ticket(new_data)

            print(f"[Tickets Cogs]   Nouvelle catégorie créée : {category.name}")

        if isinstance(result, list):
            try:
                # Tri décroissant par ticket_num pour avoir le plus récent en premier (index 0)
                result = sorted(result, key=lambda t: t.ticket_num, reverse=True)
            except AttributeError:
                print("[Tickets Cogs]   Création d'un ticket | Un des objets Ticket n'a pas d'attribut 'ticket_num'.")

        match result:
            case Ticket() as single_ticket:
                ch = guild.get_channel(single_ticket.channel_id)

                if single_ticket.is_application: #signifie que le ticket est une candidature
                    if ch:
                        await interaction.followup.send(
                            content=f"✅ - Candidature trouvée dans la base de données\n"
                                    f"✅ - La candidature a été trouver dans le serveur\n"
                                    f"{ch.mention}\n",
                            ephemeral=True
                        )
                        return
                    else:
                        await interaction.followup.send(
                            content=f"✅ - Candidature trouvée dans la base de données\n"
                                    f"❌ - Aucune candidature a été trouver dans le serveur\n"
                                    f"Si il existe vous pouvez la supprimer en toute sureté !",
                            ephemeral=True
                        )
                        return
                else: #signifie que le ticket est un ticket landa
                    if ch:
                        await interaction.followup.send(
                            content=f"✅ - Ticket trouvé dans la base de données\n"
                                    f"✅ - Le ticket a été trouver dans le serveur\n"
                                    f"{ch.mention}\n",
                            ephemeral=True
                        )
                        return
                    else:
                        await interaction.followup.send(
                            content=f"✅ - Ticket trouvé dans la base de données\n"
                                    f"❌ - Aucun ticket a été trouver dans le serveur\n"
                                    f"Si il existe vous pouvez le supprimer en toute sureté !",
                            ephemeral=True
                        )
                        return


            case list() as ticket_list if len(ticket_list) > 0:
                newest_tickets = ticket_list[:2]
                oldest_tickets = ticket_list[2:]

                for t in oldest_tickets:
                    ch = guild.get_channel(t.channel_id)
                    v_ch = guild.get_channel(t.voice_channel_id)

                    if not ch:
                        data = Ticket(
                            guild_id=interaction.guild.id,
                            user_id=t.user_id,
                            channel_id=t.channel_id,
                        )
                        self.db.supress_ticket(data)
                        continue

                    if t.is_application: # Si candidature
                        file_path = await save_channel_to_json(channel)

                        guild_staff = interaction.client.get_guild(int(GUILD_STAFF_SERVER_ID))
                        log_channel = guild_staff.get_channel(int(TICKETS_LOG_CHANNEL_ID))

                        if log_channel and file_path:
                            file_to_send = nextcord.File(file_path)
                            await log_channel.send(
                                content=f"📁 **Archive de la candidature **\nUtilisateur: {t.user_name}\n"
                                        f"Canal: {channel.name}",
                                file=file_to_send
                            )

                            print(f"[Tickets Cogs]   Archivage automatique du ticket!")

                        await ch.delete()
                        if v_ch:
                            await v_ch.delete()

                        data = Ticket(
                            guild_id=interaction.guild.id,
                            user_id=t.user_id,
                            channel_id=t.channel_id,
                        )
                        self.db.supress_ticket(data)

                    else: # Si ticket landa
                        file_path = await save_channel_to_json(channel)

                        guild_staff = interaction.client.get_guild(int(GUILD_STAFF_SERVER_ID))
                        log_channel = guild_staff.get_channel(int(TICKETS_LOG_CHANNEL_ID))

                        if log_channel and file_path:
                            file_to_send = nextcord.File(file_path)
                            await log_channel.send(
                                content=f"📁 **Archive du ticket **\nUtilisateur: {t.user_name}\n"
                                        f"Canal: {channel.name}",
                                file=file_to_send
                            )

                            print(f"[Tickets Cogs]   Archivage automatique du ticket!")

                        await ch.delete()

                        data = Ticket(
                            guild_id=interaction.guild.id,
                            user_id=t.user_id,
                            channel_id=t.channel_id,
                        )
                        self.db.supress_ticket(data)

                for t in newest_tickets:
                    ch = guild.get_channel(t.channel_id)

                    if not ch:
                        if t.voice_channel_id:
                            v_ch = interaction.guild.get_channel(t.voice_channel_id)
                            if v_ch:
                                await v_ch.delete()

                        data = Ticket(
                            guild_id=interaction.guild.id,
                            user_id=t.user_id,
                            channel_id=t.channel_id,
                        )
                        self.db.supress_ticket(data)

                    if t.is_application:
                        if type_ticket == 'c':
                            await interaction.followup.send(
                                content=f"✅ - Candidature trouvée dans la base de données\n"
                                        f"✅ - La candidature a été trouver dans le serveur\n"
                                        f"{ch.mention}\n",
                                ephemeral=True
                            )
                            return

                    if not t.is_application:
                        if type_ticket == 't':
                            await interaction.followup.send(
                                content=f"✅ - Ticket trouvé dans la base de données\n"
                                        f"✅ - Le ticket a été trouver dans le serveur\n"
                                        f"{ch.mention}\n",
                                ephemeral=True
                            )
                            return

            case _:
                pass

        current_view, prefix = views[type_ticket]

        overwrites = {
            guild.default_role: PermissionOverwrite(view_channel=False),
            member: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                        read_message_history=True),
            guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
        }

        new_channel = await guild.create_text_channel(
            name=f"{prefix}{member.name}",
            overwrites=overwrites,
            category=category
        )

        overwrites = {
            guild.default_role: PermissionOverwrite(view_channel=False),
            member: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                        read_message_history=True, speak=True, attach_files=True,
                                        connect=True,
                                        use_voice_activation=True),
            guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
        }

        await create_admin_thread(
            channel=new_channel
        )

        data = Ticket(
            guild_id=guild.id,
            category_id=category.id,
            step=step_idx,
            channel_id=new_channel.id,
            user_id=member.id,
            user_name=member.name,
            application_ticket=1 if type_ticket == 'c' else 0
        )

        if type_ticket == 'c':
            voice_channel = await guild.create_voice_channel(
                name=f"Recrutement | {member.name}",
                overwrites=overwrites,
                category=category
            )
            data.voice_channel_id = voice_channel.id


        self.db.insert_ticket(data)

        # Mise à jour de la vue et envoi du message initial dans le ticket
        current_view.update_components(interaction, data)

        if type_ticket == 'c':
            await new_channel.send(
                embeds=current_view.embd_response(data),
                view=current_view
            )
        else:
            await new_channel.send(
                embeds=current_view.embd_choice_reason(data),
                view=current_view
            )

        await interaction.followup.send(
            content=f"✅ - La/le {prefix} a été cré(e) pour {member.name} dans le serveur\n"
                    f"{new_channel.mention}\n",
            ephemeral=True
        )
        return

    @nextcord.slash_command(
        name="ticket-or-application",
        description="Ouvre le ticket ou la candidature pour l'utilisateur"
    )
    async def open_ticket(
            self,
            interaction: nextcord.Interaction,
            type_ticket: str = nextcord.SlashOption(
                name="type_ticket",
                required=True,
                description="Choisissez le type de ticket",
                choices={
                    "Ticket": "t",
                    "Candidature": "c"
                }
            )
    ):
        await interaction.response.defer(ephemeral=True)

        step_idx = 0
        guild = interaction.guild
        member = interaction.user

        category = None

        result = self.db.get_tickets(guild.id, member.id)

        ticketview = OpenTicketsView(db=self.db)
        applicationview = OpenApplicationsView(db=self.db)

        views = {
            't': (ticketview, "🐍-ticket-"),  # La vue et le préfixe
            'c': (applicationview, "✉️-candidature-")
        }

        cat_results = self.db.get_cat_ticket(
            guild_id=interaction.guild.id,
        )

        match cat_results:
            case TicketGuilds():
                category = guild.get_channel(cat_results.category_id)

                if category:
                    print(f"[Tickets Cogs]   Ouverture d'un ticket | "
                          f"Catégorie déjà existante dans la base de données")
            case list() as cat_list if len(cat_list) > 0:
                print(f"[Tickets Cogs]   Nettoyage de {len(cat_list)} anciennes catégories...")

                for config in cat_list[:]:  # On itère sur une copie pour pouvoir supprimer sans erreur d'index
                    channel = guild.get_channel(config.category_id)
                    if channel:
                        await channel.delete()
                    self.db.supress_cat_ticket(config)

            case _:
                pass

        if category is None:
            await interaction.followup.send(
                content=f"❌ - Erreur lors de la création du ticket\n"
                        f"❌ - Contacte le staff, la catégorie dédiée aux tickets n'existe pas\n",
                ephemeral=True
            )
            return

        if isinstance(result, list):
            try:
                # Tri décroissant par ticket_num pour avoir le plus récent en premier (index 0)
                result = sorted(result, key=lambda t: t.ticket_num, reverse=True)
            except AttributeError:
                print("[Tickets Cogs]   Création d'un ticket | Un des objets Ticket n'a pas d'attribut 'ticket_num'.")

        match result:
            case Ticket() as single_ticket:
                ch = guild.get_channel(single_ticket.channel_id)

                if single_ticket.is_application:  # signifie que le ticket est une candidature
                    if ch:
                        await interaction.followup.send(
                            content=f"✅ - Ta candidature a été trouver dans le serveur\n"
                                    f"{ch.mention}\n",
                            ephemeral=True
                        )
                        return
                    else:
                        await interaction.followup.send(
                            content=f"❌ - Aucune candidature a été trouver dans le serveur\n"
                                    f"Si il existe contacte un modérateur pour le supprimer !",
                            ephemeral=True
                        )
                        return
                else:  # signifie que le ticket est un ticket landa
                    if ch:
                        await interaction.followup.send(
                            content=f"✅ - Ton ticket a été trouver dans le serveur\n"
                                    f"{ch.mention}\n",
                            ephemeral=True
                        )
                        return
                    else:
                        await interaction.followup.send(
                            content=f"❌ - Aucun ticket a été trouver dans le serveur\n"
                                    f"Si il existe contacte un modérateur pour le supprimer !",
                            ephemeral=True
                        )
                        return

            case list() as ticket_list if len(ticket_list) > 0:
                newest_tickets = ticket_list[:2]
                oldest_tickets = ticket_list[2:]

                for t in oldest_tickets:
                    ch = guild.get_channel(t.channel_id)
                    v_ch = guild.get_channel(t.voice_channel_id)

                    if not ch:
                        data = Ticket(
                            guild_id=interaction.guild.id,
                            user_id=t.user_id,
                            channel_id=t.channel_id,
                        )
                        self.db.supress_ticket(data)
                        continue

                    if t.is_application:  # Si candidature
                        file_path = await save_channel_to_json(channel)

                        guild_staff = interaction.client.get_guild(int(GUILD_STAFF_SERVER_ID))
                        log_channel = guild_staff.get_channel(int(TICKETS_LOG_CHANNEL_ID))

                        if log_channel and file_path:
                            file_to_send = nextcord.File(file_path)
                            await log_channel.send(
                                content=f"📁 **Archive de la candidature **\nUtilisateur: {t.user_name}\n"
                                        f"Canal: {channel.name}",
                                file=file_to_send
                            )

                            print(f"[Tickets Cogs]   Archivage automatique du ticket!")

                        await ch.delete()
                        if v_ch:
                            await v_ch.delete()

                        data = Ticket(
                            guild_id=interaction.guild.id,
                            user_id=t.user_id,
                            channel_id=t.channel_id,
                        )
                        self.db.supress_ticket(data)

                    else:  # Si ticket landa
                        file_path = await save_channel_to_json(channel)

                        guild_staff = interaction.client.get_guild(int(GUILD_STAFF_SERVER_ID))
                        log_channel = guild_staff.get_channel(int(TICKETS_LOG_CHANNEL_ID))

                        if log_channel and file_path:
                            file_to_send = nextcord.File(file_path)
                            await log_channel.send(
                                content=f"📁 **Archive du ticket **\nUtilisateur: {t.user_name}\n"
                                        f"Canal: {channel.name}",
                                file=file_to_send
                            )

                            print(f"[Tickets Cogs]   Archivage automatique du ticket!")

                        await ch.delete()

                        data = Ticket(
                            guild_id=interaction.guild.id,
                            user_id=t.user_id,
                            channel_id=t.channel_id,
                        )
                        self.db.supress_ticket(data)

                for t in newest_tickets:
                    ch = guild.get_channel(t.channel_id)

                    if not ch:
                        if t.voice_channel_id:
                            v_ch = interaction.guild.get_channel(t.voice_channel_id)
                            if v_ch:
                                await v_ch.delete()

                        data = Ticket(
                            guild_id=interaction.guild.id,
                            user_id=t.user_id,
                            channel_id=t.channel_id,
                        )
                        self.db.supress_ticket(data)

                    if t.is_application:
                        if type_ticket == 'c':
                            await interaction.followup.send(
                                content=f"✅ - Ta candidature a été trouver dans le serveur\n"
                                        f"{ch.mention}\n",
                                ephemeral=True
                            )
                            return

                    if not t.is_application:
                        if type_ticket == 't':
                            await interaction.followup.send(
                                content=f"✅ - Ton ticket a été trouver dans le serveur\n"
                                        f"{ch.mention}\n",
                                ephemeral=True
                            )
                            return

            case _:
                pass

        current_view, prefix = views[type_ticket]

        overwrites = {
            guild.default_role: PermissionOverwrite(view_channel=False),
            member: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                        read_message_history=True),
            guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
        }

        new_channel = await guild.create_text_channel(
            name=f"{prefix}{member.name}",
            overwrites=overwrites,
            category=category
        )

        overwrites = {
            guild.default_role: PermissionOverwrite(view_channel=False),
            member: PermissionOverwrite(view_channel=True, send_messages=False, read_messages=True,
                                        read_message_history=True, speak=True, attach_files=True,
                                        connect=True,
                                        use_voice_activation=True),
            guild.me: PermissionOverwrite(view_channel=True, send_messages=True)
        }

        await create_admin_thread(
            channel=new_channel
        )

        data = Ticket(
            guild_id=guild.id,
            category_id=category.id,
            step=step_idx,
            channel_id=new_channel.id,
            user_id=member.id,
            user_name=member.name,
            application_ticket=1 if type_ticket == 'c' else 0
        )

        if type_ticket == 'c':
            voice_channel = await guild.create_voice_channel(
                name=f"Recrutement | {member.name}",
                overwrites=overwrites,
                category=category
            )
            data.voice_channel_id = voice_channel.id

        self.db.insert_ticket(data)

        # Mise à jour de la vue et envoi du message initial dans le ticket
        current_view.update_components(interaction, data)

        if type_ticket == 'c':
            await new_channel.send(
                embeds=current_view.embd_response(data),
                view=current_view
            )
        else:
            await new_channel.send(
                embeds=current_view.embd_choice_reason(),
                view=current_view
            )

        await interaction.followup.send(
            content=f"✅ - Ta/ton {prefix} a été cré(e) rien que pour toi dans le serveur\n"
                    f"{new_channel.mention}\n",
            ephemeral=True
        )
        return


    @nextcord.slash_command(
        name="close-ticket-of-user",
        description="Ferme le ticket/la candidature d'un utilisateur",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def close_user_ticket(
            self, interaction: nextcord.Interaction, channel: nextcord.TextChannel
    ):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        result = self.db.get_open_ticket(guild.id, channel.id)

        print(f"{result}")
        print(f"{isinstance(result, Ticket)}")
        print(f"{type(result)}")

        if isinstance(result, Ticket):
            target_ch = guild.get_channel(result.channel_id)

            if target_ch:

                file_path = await save_channel_to_json(target_ch)

                guild_staff = interaction.client.get_guild(int(GUILD_STAFF_SERVER_ID))
                log_channel = guild_staff.get_channel(int(TICKETS_LOG_CHANNEL_ID))

                if log_channel and file_path:
                    file_to_send = nextcord.File(file_path)
                    await log_channel.send(
                        content=f"📁 **Archive du ticket **\nUtilisateur: {result.user_name}\n"
                                f"Canal: {target_ch.name}",
                        file=file_to_send
                    )

                await interaction.followup.send(
                    content=f"✅ - Ticket va bientot se fermer et être archiver!",
                    ephemeral=True
                )

                self.db.supress_ticket(result)

                await asyncio.sleep(10)

                await target_ch.delete()

                if result.voice_channel_id:
                    target_voice_ch = guild.get_channel(result.voice_channel_id)

                    if target_voice_ch:
                        await target_voice_ch.delete()
                return
            else:
                if result:
                    self.db.supress_ticket(result)
                await interaction.followup.send(
                    content=f"✅ - Suppression du ticket dans la base de données\n"
                        f"❌ - Aucun ticket ouvert dans le serveur\n"
                        f"❌ - Aucun archivage!\n"
                        f"Si il existe vous pouvez le supprimer en toute sureté !",
                    ephemeral=True
                )
                return

        else:
            await interaction.followup.send(
                content=f"❌ - Aucun ticket a été trouver dans la base de données\n"
                    f"❌ - Aucun ticket a été trouver dans le serveur\n"
                    f"❌ - Aucun archivage!\n"
                    f"Si il existe vous pouvez le supprimer en toute sureté !",
                ephemeral=True
            )



def setup(bot):
    bot.add_cog(Tickets(bot))