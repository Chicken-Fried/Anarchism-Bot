import nextcord

from typing import List
from .models.error_models import ErrorEmbed, ErrorEmbedField

def error_embed(e_embeds: List[ErrorEmbed], e_embeds_fields: List[ErrorEmbedField] = None) -> List[nextcord.Embed]:
    embeds = []
    for idx, e_embed in enumerate(e_embeds):
        embed = nextcord.Embed(
            title=e_embed.title,
            description=e_embed.description,
            color=e_embed.color,
            type=e_embed.type,
            url=e_embed.url,
        )

        if e_embeds_fields:
            for e_embed_field in e_embeds_fields:
                if e_embed_field.number == idx+1:
                    embed.add_field(
                        name=e_embed_field.name,
                        value=e_embed_field.value,
                        inline=e_embed_field.inline,
                    )
                else:
                    continue

        embeds.append(embed)

    return embeds