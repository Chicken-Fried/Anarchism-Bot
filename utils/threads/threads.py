import nextcord
import asyncio
import os

from embed.tickets_embeds import alert_ticket_embed, AlertTicketEmbed
from views.thread_views import ThreadView

from dotenv import load_dotenv
load_dotenv()

GUILD_SQB_SERVER_ID = os.getenv('GUILD_SQB_SERVER_ID')
SQB_STAFF_ID = os.getenv('SQB_SERVER_STAFF_ROLE_ID')

GUILD_COMMUNITY_SERVER_ID = os.getenv('COMMUNITY_SERVER_GUILD_ID')
COMMUNITY_STAFF_ID = os.getenv('COMMUNITY_STAFF_ROLE_ID')

ROLES_ID = {
    int(GUILD_SQB_SERVER_ID): int(SQB_STAFF_ID),
    int(GUILD_COMMUNITY_SERVER_ID): int(COMMUNITY_STAFF_ID)
}

async def create_admin_thread(channel: nextcord.TextChannel):
    """
    Crée un thread privé et ajoute tous les membres ayant le rôle Admin.
    Note : Nécessite un Boost Niveau 2 sur le serveur.
    """
    view = ThreadView()

    try:
        # 1. Création du thread privé
        thread = await channel.create_thread(
            name="🔒 Staff-discussion",
            type=nextcord.ChannelType.private_thread
        )

        # 2. On récupère le rôle staff
        guild_id = channel.guild.id
        staff_role_id = ROLES_ID.get(guild_id)

        if staff_role_id:
            role = channel.guild.get_role(staff_role_id)
            if not role:
                return None

            at_embeds = AlertTicketEmbed(
                title=f"🧾 | Un utilisateur a ouvert une candidature !",
                description=(
                    f"N'hésitez pas à finaliser sa candidature et à le recruter "
                    f"dès que vous êtes disponible !\n"
                ),
            )

            await thread.send(
                content=f"{role.mention}",
                embed=alert_ticket_embed(
                            at_embed=at_embeds
                        ),
                view=view
            )

        return thread

    except Exception as e:
        print(f"Erreur : {e}")
        return None
