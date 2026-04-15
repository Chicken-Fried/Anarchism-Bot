import nextcord


class TicketView(nextcord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @nextcord.ui.button(
        labels="Ouvrir un ticket",
        style=nextcord.ButtonStyle.primary,
        emoji="📥",
        custom_id="open_ticket_btn")
    async def open_ticket(self, button: nextcord.ui.button, interaction: nextcord.Interaction):
        """
        Ouvre un ticket via un viewer pour un utilisateur

        :param button: nextcord.ui.Button
        :param interaction: nextcord.Interaction
        :return:
        """
        guild = interaction.guild
        user = interaction.user

        #Vérifier si l'utilisateur a déjà un ticket ouvert (optionnel mais conseillé)
        existing_chan = nextcord.utils.get(guild.text_channels, name=f"ticket-{user.name.lower()}")
        if existing_chan:
            return await interaction.response.send_message(f"Tu as déjà un ticket ouvert ici : "
                                                           f"{existing_chan.mention}", ephemeral=True)

        #Définir les permission du salon textuel
        #Seul l'utilisateur et le staff voient le salon
        overwrites = {
            guild.default_role: nextcord.PermissionOverwrite(read_messages=False),
            user: nextcord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: nextcord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        #Création du salon (tu peux ajouter une catégorie spécifique)
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{user.name}",
            overwrites=overwrites,
            topic=f"Ticket de {user.id}"
        )

        await interaction.response.send_message(f"Ticket créé ! {ticket_channel.mention}", ephemeral=True)

        #Message de bienvenue dans le ticket avec un bouton pour fermer
        embed = nextcord.Embed(
            title="Support Technique",
            description=f"Bonjour {user.mention},\nExpliquez votre problème ici. Un membre du staff vous répondra bientôt.",
            color=nextcord.Color.green()
        )
        await ticket_channel.send(embed=embed, view=CloseTicketView())