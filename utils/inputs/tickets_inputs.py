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


"""class StartAbsentDateModal(Modal):
    def __init__(self):
        super().__init__(title="Candidature")

        self.date_input = TextInput(
            label="Date d'entrée d'absence [JJ/MM/AAAA]",
            style=nextcord.TextInputStyle.short,
            placeholder="Ex: 15/08/2003",
            required=True,
            custom_id="absent_start_date"
        )

        self.add_item(self.date_input)

    async def callback(self, interaction: nextcord.Interaction):
        date_str = self.date_input.value

        # Validation Regex (Format JJ/MM/AAAA uniquement)
        pattern = r'^\d{2}/\d{2}/\d{4}$'

        if not re.match(pattern, date_str):
            await interaction.response.send_message(
                "❌ Format invalide. Utilisez JJ/MM/AAAA.",
                ephemeral=True
            )
            return

        # Vérification de la validité (ex: pas le 32/13/2025)
        try:
            start_date = datetime.strptime(date_str, '%d/%m/%Y')
        except ValueError:
            await interaction.response.send_message(
                "❌ Date invalide.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Date validée: {start_date.strftime('%d/%m/%Y')}",
            ephemeral=True
        )

        # Traitement réussi
        await interaction.response.send_modal(EndAbsentDateModal(start_date=date_str))


class EndAbsentDateModal(Modal):
    def __init__(self, start_date: str=None):
        super().__init__(title="Candidature")

        self.start_date_str = start_date

        self.date_input = TextInput(
            label="Date de fin d'absence [JJ/MM/AAAA] OU Aucune date",
            style=nextcord.TextInputStyle.short,
            placeholder="Ex: 15/08/2003",
            required=True,
            custom_id="absent_end_date"
        )

        self.add_item(self.date_input)

    async def callback(self, interaction: nextcord.Interaction):
        date_str = self.date_input.value.lower().strip()

        #Condition 1 : "Aucune date" (variations acceptées)
        no_date_variants = ["aucune date", "pas de date", "none", "-", "."]

        guild_sqb = interaction.client.get_guild(int(SQB_GUILD_ID))
        guild_staff = interaction.client.get_guild(int(STAFF_GUILD_ID))

        #Fonction 1: Fonction pour envoyer dans un channel précis à une guild précise
        async def send_to_channel(guild, channel_id):
            if guild:
                channel = guild.get_channel(int(channel_id))
                if channel:
                    await channel.send(embed=embed)
                else:
                    print(f"[Utils Tickets_input]     : "
                          f"Erreur salon introuvable pour envoyer le message d'absence {channel_id}")
            else:
                print(f"[Utils Tickets_input]     : "
                      f"Erreur guild introuvable pour envoyer le message d'absence dans le salon {channel_id}")

        if date_str in no_date_variants:
            await interaction.response.send_message(
                "✅ Aucune date de fin enregistrée.",
                ephemeral=True
            )

            embed = nextcord.Embed(
                title="📢 Nouveau ticket d'absence enregistré !",
                description="Une nouvelle demande d'absence vient d'être validée.",
                color=nextcord.Color.green()
            )

            # Ajout des informations dans les champs (fields)
            embed.add_field(name="👤 Utilisateur", value=interaction.user.mention, inline=True)
            embed.add_field(name="📅 Date de début", value=self.start_date_str.strftime('%d/%m/%Y'), inline=True)

            # Gestion de la date de fin (si elle existe)
            date_end = "Date indéfinie"
            embed.add_field(name="📅 Date de fin", value=date_end, inline=True)

            embed.set_footer(text="Système de Ticket - PYTHON")
            embed.timestamp = nextcord.utils.utcnow()

            await send_to_channel(guild_staff, STAFF_SERVER_CHANNEL_ID)
            await send_to_channel(guild_sqb, SQB_SERVER_CHANNEL_ID)

            await interaction.response.send_message(
                "✅ Vos dates d'absence ont été enregistrées et transmises au staff.", ephemeral=True)

            print(f"[Ticket Absence]     :"
                  f"Absence pour l'utlisateur {interaction.user.name} aux dates => "
                  f"{self.start_date_str.strftime('%d/%m/%Y')} - Date indéfinie")

            return

        #Condition 2 : Validation du format JJ/MM/AAAA
        pattern = r'^\d{2}/\d{2}/\d{4}$'

        if not re.match(pattern, date_str):
            await interaction.response.send_message(
                "❌ Format invalide. Utilisez JJ/MM/AAAA ou 'Aucune date'.",
                ephemeral=True
            )
            return

        #Condition 3 : Vérification de la validité de la date
        try:
            end_date = datetime.strptime(date_str, '%d/%m/%Y')
        except ValueError:
            await interaction.response.send_message(
                "❌ Date invalide.",
                ephemeral=True
            )
            return

        #Condition 4 : Vérification que la date est POSTÉRIEURE à la date de début
        if self.start_date_str:
            try:
                start_date = datetime.strptime(self.start_date_str, '%d/%m/%Y')

                if end_date <= start_date:
                    await interaction.response.send_message(
                        f"❌ La date de fin doit être postérieure à la date de début ({start_date.strftime('%d/%m/%Y')}).",
                        ephemeral=True
                    )
                    return

            except ValueError:
                pass

        await interaction.response.send_message(
            f"✅ Date validée : {end_date.strftime('%d/%m/%Y')}",
            ephemeral=True
        )

        embed = nextcord.Embed(
            title="📢 Nouveau ticket d'absence enregistré !",
            description="Une nouvelle demande d'absence vient d'être validée.",
            color=nextcord.Color.green()
        )

        # Ajout des informations dans les champs (fields)
        embed.add_field(name="👤 Utilisateur", value=interaction.user.mention, inline=True)
        embed.add_field(name="📅 Date de début", value=self.start_date_str.strftime('%d/%m/%Y'), inline=True)

        # Gestion de la date de fin (si elle existe)
        embed.add_field(name="📅 Date de fin", value=end_date.strftime('%d/%m/%Y'), inline=True)

        embed.set_footer(text="Système de Ticket - PYTHON")
        embed.timestamp = nextcord.utils.utcnow()

        await send_to_channel(guild_staff, STAFF_SERVER_CHANNEL_ID)
        await send_to_channel(guild_sqb, SQB_SERVER_CHANNEL_ID)

        await interaction.response.send_message(
            "✅ Vos dates d'absence ont été enregistrées et transmises au staff.", ephemeral=True)

        print(f"[Ticket Absence]     :"
              f"Absence pour l'utlisateur {interaction.user.name} aux dates => "
              f"{self.start_date_str.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}")"""

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

