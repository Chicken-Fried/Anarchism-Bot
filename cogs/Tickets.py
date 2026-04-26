import os
import nextcord
import asyncio
from nextcord.ext import commands
from nextcord import PermissionOverwrite

from views.tickets_views import OpenTicketsView
from views.applications_views import OpenApplicationsView
from utils.tickets_log import save_channel_to_json
from database.models.tickets_class import Ticket, TicketViewChannels

# ── PARAMETRES INITIALS ────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv()
TICKETS_LOG_CHANNEL_ID = os.getenv('STAFF_SERVER_TICKETS_LOG_CHANNEL_ID')
GUILD_STAFF_SERVER_ID = os.getenv('GUILD_STAFF_SERVER_ID')


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
                self.db.supress_ch_ticket(result)

                await asyncio.sleep(10)

                await target_ch.delete()

                if result.voice_channel_id:
                    target_voice_ch = guild.get_channel(result.voice_channel_id)

                    if target_voice_ch:
                        await target_voice_ch.delete()
                return
            else:
                if result:
                    self.db.supress_ch_ticket(result)
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