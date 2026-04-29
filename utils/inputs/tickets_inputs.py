import re
import os
import asyncio
from datetime import datetime, date
import nextcord
from nextcord.ui import Modal, TextInput

from dotenv import load_dotenv

from database.db_tickets import TicketsDB

load_dotenv()
SQB_GUILD_ID = os.getenv('GUILD_SQB_SERVER_ID')
STAFF_GUILD_ID  = os.getenv('GUILD_STAFF_SERVER_ID')

SQB_SERVER_CHANNEL_ID = os.getenv('SQB_SERVER_CHANNEL_ID')
STAFF_SERVER_CHANNEL_ID  = os.getenv('STAFF_SERVER_CHANNEL_ID')

class AbsentModal(nextcord.ui.Modal):
    def __init__(self, db: TicketsDB):
        super().__init__(title="Candidature")

        self.db = db

        self.start_date = TextInput(
            label="Date de début d'absence",
            style=nextcord.TextInputStyle.short,
            placeholder="Format demandé - [JJ/MM/AAAA]",
            required=True
        )
        self.end_date = TextInput(
            label="Date de fin d'absence",
            style=nextcord.TextInputStyle.short,
            placeholder="Format demandé - [JJ/MM/AAAA] ou 'aucune date'",
            required=True
        )
        self.reason = TextInput(
            label="Raison de l'absence",
            style=nextcord.TextInputStyle.short,
            placeholder="[Facultatif]",
            required=False
        )

        self.add_item(self.start_date)
        self.add_item(self.end_date)
        self.add_item(self.reason)

    async def callback(self, interaction: nextcord.Interaction):
        start_str = self.start_date.value.strip()
        end_str = self.end_date.value.lower().strip()
        reason = self.reason.value

        pattern = '^\\d{2}/\\d{2}/\\d{4}$'
        no_date_variants = ["aucune date", "pas de date", "none", "-", "."," ",""]

        now = datetime.now()

        # ─── VALIDATION DATE DE DÉBUT ───
        if not re.match(pattern, start_str):
            return await interaction.response.send_message(
                "❌ Format date de début invalide (JJ/MM/AAAA).\n"
                "Recliquer sur 'Introduire une absence' pour poursuivre.",
                ephemeral=True
            )

        try:
            start_date = datetime.strptime(start_str, '%d/%m/%Y')
        except ValueError:
            return await interaction.response.send_message(
                "❌ Date de début invalide.\n"
                "Recliquer sur 'Introduire une absence' pour poursuivre.",
                ephemeral=True
            )

        if end_str in no_date_variants:
            end_date = None

            if start_date < now:
                return await interaction.response.send_message(
                    "❌ La date de début est dans le passé.\n"
                    "Recliquer sur 'Introduire une absence' pour poursuivre.",
                    ephemeral=True
                )

        else:
            if not re.match(pattern, end_str):
                return await interaction.response.send_message(
                    "❌ Format date de fin invalide.\n"
                    "Recliquer sur 'Introduire une absence' pour poursuivre.",
                    ephemeral=True
                )

            try:
                end_date = datetime.strptime(end_str, '%d/%m/%Y')
            except ValueError:
                return await interaction.response.send_message(
                    "❌ Date de fin invalide.\n"
                    "Recliquer sur 'Introduire une absence' pour poursuivre.",
                    ephemeral=True
                )

            if end_date <= start_date:
                return await interaction.response.send_message(
                    "❌ La date de fin doit être après la date de début.\n"
                    "Recliquer sur 'Introduire une absence' pour poursuivre.",
                    ephemeral=True
                )

            if end_date < now or start_date < now:
                return await interaction.response.send_message(
                    "❌ La date de fin et/ou la date de début est/sont dans le passé.\n"
                    "Recliquer sur 'Introduire une absence' pour poursuivre.",
                    ephemeral=True
                )


        # ─── EMBED ───
        embed = nextcord.Embed(
            title="📢 Nouveau ticket d'absence",
            description="Une demande d'absence a été enregistrée.",
            color=nextcord.Color.green()
        )

        embed.add_field(name="👤 Utilisateur", value=interaction.user.mention)
        embed.add_field(name="📅 Début", value=start_date.strftime('%d/%m/%Y'))

        if end_date:
            embed.add_field(name="📅 Fin", value=end_date.strftime('%d/%m/%Y'))

            print(f"[Ticket Absence]     :"
                  f"Absence pour l'utlisateur {interaction.user.name} aux dates => "
                  f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}")
        else:
            embed.add_field(name="📅 Fin", value="Date indéfinie")

            print(f"[Ticket Absence]     :"
                  f"Absence pour l'utlisateur {interaction.user.name} aux dates => "
                  f"{start_date.strftime('%d/%m/%Y')} - Date indéfinie")

        if reason:
            embed.add_field(
                name="Raison de l'absence",
                value=reason,
                inline=False
            )
        else:
            embed.add_field(
                name="Raison de l'absence",
                value="Aucune",
                inline=False
            )

        embed.timestamp = nextcord.utils.utcnow()

        ticket = self.db.get_open_ticket(guild_id=interaction.guild_id, channel_id=interaction.channel.id)

        # ─── ENVOI ───
        guild_sqb = interaction.client.get_guild(int(SQB_GUILD_ID))
        guild_staff = interaction.client.get_guild(int(STAFF_GUILD_ID))

        channel = interaction.guild.get_channel(interaction.channel.id)

        async def send_to_channel(guild, channel_id):
            if guild:
                channel = guild.get_channel(int(channel_id))
                if channel:
                    await channel.send(embed=embed)

        await send_to_channel(guild_staff, STAFF_SERVER_CHANNEL_ID)
        await send_to_channel(guild_sqb, SQB_SERVER_CHANNEL_ID)

        # ─── RÉPONSE UNIQUE ───
        await interaction.response.send_message(
            "✅ - Votre absence a été enregistrée et envoyée au staff."
            "Ce ticket sera supprimé",
            ephemeral=True
        )

        await asyncio.sleep(10)

        await channel.delete()

        self.db.supress_ch_ticket(ticket)

