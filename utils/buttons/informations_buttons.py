import nextcord
from nextcord import PermissionOverwrite


class OpenTicket(nextcord.ui.Button):

    def __init__(self):
        super().__init__(label="Ouvrir un ticket", style=nextcord.ButtonStyle.green, custom_id="open_ticket")