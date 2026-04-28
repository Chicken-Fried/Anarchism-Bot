import nextcord

from utils.buttons.thread_buttons import UrlGoogleSheetApplicationButton


class ThreadView(nextcord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(UrlGoogleSheetApplicationButton())
