import nextcord
from unicodedata import category


class CategorySelect(nextcord.ui.ChannelSelect):

    def __init__(self):
        super().__init__(
            placeholder="Choisissez la catégorie des escadrons",
            channel_types=[nextcord.ChannelType.category],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: nextcord.Interaction):
        view = self.view
        category = self.values[0]

        if not interaction.data:
            print('Aucune interaction')
            return

        if len(self.values) > self.view.children[0].max_values:
            return

        view.data["category"] = category.id
        view.names["category"] = category.name

        view.step_index += 1

        print(view.step_index)

        view.update_components()

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )


class PilotRoleSelect(nextcord.ui.RoleSelect):

    def __init__(self):
        super().__init__(
            placeholder="Choisissez le rôle des pilotes",
            min_values=1,
            max_values=3
        )

    async def callback(self, interaction: nextcord.Interaction):
        view = self.view
        roles = self.values

        print(f"Roles: {roles}")

        if not interaction.data:
            print('Aucune interaction')
            return

        if len(self.values) > self.view.children[0].max_values:
            return

        guild = interaction.guild

        view.data["pilot_role"] = []
        view.names["pilot_role"] = []

        for role in roles:
            view.data["pilot_role"].append(role.id)
            view.names["pilot_role"].append(role.name)

        view.step_index += 1

        print(view.step_index)

        view.update_components()

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )


class LeaderRoleSelect(nextcord.ui.RoleSelect):

    def __init__(self):
        super().__init__(
            placeholder="Choisissez le rôle leader",
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: nextcord.Interaction):
        view = self.view

        if not interaction.data:
            print('Aucune interaction')
            return

        if len(interaction.data["values"]) > self.view.children[0].max_values:
            return

        guild = interaction.guild

        view.data["leader_role"] = interaction.data["values"]

        role = guild.get_role(interaction.data["values"])
        view.names["pilot_role"] = role.name

        view.step_index += 1
        view.update_components()

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )


class LogChannelSelect(nextcord.ui.ChannelSelect):

    def __init__(self):
        super().__init__(
            placeholder="Choisissez le salon de logs",
            channel_types=[nextcord.ChannelType.text],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: nextcord.Interaction):
        view = self.view

        if not interaction.data:
            print('Aucune interaction')
            return

        if len(interaction.data["values"]) > self.view.children[0].max_values:
            return

        guild = interaction.guild

        view.data["log_channel"] = interaction.data["values"]

        channel = guild.get_channel(interaction.data["values"])
        view.names["log_channel"] = channel.name

        view.step_index += 1
        view.update_components()

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )