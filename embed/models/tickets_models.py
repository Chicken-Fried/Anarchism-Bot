from dataclasses import dataclass
from nextcord import Color
from typing import Literal

@dataclass
class AlertTicketEmbed:
    title:           str
    description:     str | None = None
    fields:          list['AlertTicketEmbedField'] | None = None
    url:             str | None = None
    type:            Literal["rich", "image", "video", "gifv", "article", "link"] = "rich"
    color:           Color = Color.dark_green()

@dataclass
class AlertTicketEmbedField:
    name:            str
    value:           str
    number:          int = 1
    inline:          bool = False
