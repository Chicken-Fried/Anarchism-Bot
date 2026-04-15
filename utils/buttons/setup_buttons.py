import nextcord

class NextButton(nextcord.ui.Button):

    def __init__(self):
        super().__init__(label="Suivant", style=nextcord.ButtonStyle.green)

    async def callback(self, interaction: nextcord.Interaction):

        view = self.view
        view.error_page = list(view.data.keys())[view.step_index]

        #if view.step_index < len(view.STEPS) - 1 and view.data:
            #view.step_index += 1

        view.update_components()

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )


class PreviousButton(nextcord.ui.Button):

    def __init__(self):
        super().__init__(label="Retour", style=nextcord.ButtonStyle.grey)

    async def callback(self, interaction: nextcord.Interaction):

        view = self.view

        if view.step_index > 0:
            view.step_index -= 1

        view.update_components()

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )


class CancelButton(nextcord.ui.Button):

    def __init__(self):
        super().__init__(label="Annuler", style=nextcord.ButtonStyle.red)

    async def callback(self, interaction: nextcord.Interaction):

        view = self.view

        for item in view.children:
            item.disabled = True

        await interaction.response.edit_message(
            content="Setup annulé.",
            view=view
        )

class EndButton(nextcord.ui.Button):

    def __init__(self):
        super().__init__(label="Terminer", style=nextcord.ButtonStyle.green)

    async def callback(self, interaction: nextcord.Interaction):

        view = self.view

        print(view.data)

        for item in view.children:
            item.disabled = True

        await interaction.response.edit_message(
            content="✅ Configuration terminée.",
            view=view
        )