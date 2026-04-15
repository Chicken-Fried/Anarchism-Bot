from dataclasses import dataclass
from nextcord import Color
from typing import Literal

@dataclass
class ErrorEmbed:
    title:           str
    description:     str | None = None
    fields:          list[ErrorEmbedField] | None = None
    url:             str | None = None
    type:            Literal["rich", "image", "video", "gifv", "article", "link"] = "rich"
    color:           Color = Color.dark_red()

@dataclass
class ErrorEmbedField:
    name:            str
    value:           str
    number:          int = 1
    inline:          bool = False
