import nextcord

from typing import List
from .models.tickets_models import AlertTicketEmbed

def alert_ticket_embed(
        at_embed: AlertTicketEmbed
) -> nextcord.Embed:
    embed = nextcord.Embed(
        title=at_embed.title,
        description=at_embed.description,
        color=at_embed.color,
        type=at_embed.type,
        url=at_embed.url,
    )

    return embed