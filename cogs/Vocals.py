import nextcord
from nextcord.ext import commands

# ── PARAMETRES INITIALS ────────────────────────────────────────────────
HUB_NAME = "[➕] Créer un vocal"
TEMP_PREFIX = "[🐍] Vocal de"


class Vocals(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    async def handle_leave(self, channel: nextcord.VoiceChannel):
        """
        Supprime le salon s'll est vide et n'est pas un salon permanent.
        On vérifie si il y a personne dans le salon.

        :param channel: nextcord.VoiceChannel
        :return:
        """
        #Condition 1: Le salon doit être vide
        if len(channel.members) > 0:
            return

        #Condition 2: Vérification si le salon est temporaire
        is_temp = "🐍" or "Vocal de" in channel.name
        is_hub = "[➕]" in channel.name

        if is_temp and not is_hub:
            try:
                await channel.delete()
                print(f"[Vocals Cog] Nettoyage:      Salon {channel.name} supprimé.")
            except nextcord.NotFound:
                pass
            except nextcord.Forbidden:
                print(f"[Vocals Cog]    Erreur:      Permission insuffisantes pour supprimer le salon {channel.name}.")

    async def handle_join(self, member: nextcord.Member, channel: nextcord.VoiceChannel):
        """
        Crée un salon si le membre rejoint le hub.

        :param member: nextcord.Member
        :param channel: nextcord.VoiceChannel
        :return:
        """
        # Condition 1: Vérifie le nom du salon
        is_hub = "[➕]" in channel.name

        if is_hub:
            try:
                category = channel.category

                new_channel = await category.create_voice_channel(
                    name=f"[🐍] Vocal de {member.display_name}",
                    overwrites=channel.overwrites
                )
                await member.move_to(new_channel)

            except nextcord.NotFound:
                pass

            except nextcord.Forbidden:
                print(f"[Vocals Cog]    Erreur:      Permission insuffisantes pour créer le salon {channel.name}.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: nextcord.Member, before: nextcord.VoiceChannel,
                                    after: nextcord.VoiceChannel):
        #Condition 1: Ignore si les événements inutiles aparaissent
        if before.channel == after.channel:
            return

        b_channel = before.channel
        a_channel = after.channel

        #Condition 2: On verifie que le channel avant modification existe
        # ── LOGIQUE DE DEPART ────────────────────────────────────────────────
        if b_channel:
            #Condition 3: On vérifie si le channel a le nom suivant => [🐍] Vocal de
            #Et qu'il ne possède plus aucune personne dans le channel
            if TEMP_PREFIX in b_channel.name and len(b_channel.members) == 0:
                try:
                    await b_channel.delete()
                    print(f"[Vocals Cog] Nettoyage:      "
                          f"Vocal {b_channel.name} supprimé.")

                except nextcord.Forbidden:
                    print(f"[Vocals Cog]    Erreur:      "
                          f"Permission insuffisantes pour supprimer le vocal {b_channel.name}.")

                except nextcord.NotFound:
                    print(f"[Vocals Cog]    Erreur:      "
                          f"Le salon {b_channel.name} a déjà été supprimer ou est introuvable.")

                except nextcord.HTTPException as e:
                    print(f"[Vocals Cog]    Erreur:      "
                          f"Une erreur HTTP inconnue est survenue : {e.status} - {e.text}")


        #Condition 3: On verifie que le channel après modification existe
        # ── LOGIQUE D'ARRIVEE ────────────────────────────────────────────────
        if a_channel:
            if HUB_NAME in a_channel.name:
                try:
                    category = a_channel.category

                    new_channel = await category.create_voice_channel(
                        name=f"{TEMP_PREFIX} {member.display_name}",
                        overwrites=a_channel.overwrites
                    )

                    await member.move_to(new_channel)
                    print(f"[Vocals Cog] Action:         "
                          f"Le vocal {new_channel.name} a été créer.")

                except nextcord.Forbidden:
                    print(f"[Vocals Cog]    Erreur:      "
                          f"Permission insuffisantes pour créer le vocal {a_channel.name}.")

                except nextcord.NotFound:
                    print(f"[Vocals Cog]    Erreur:      "
                          f"Le salon {a_channel.name} est introuvable.")

                except nextcord.HTTPException as e:
                    print(f"[Vocals Cog]    Erreur:      "
                          f"Une erreur HTTP inconnue est survenue : {e.status} - {e.text}")

    @nextcord.slash_command(
        name="add-voice-channel",
        description="Ajoute le vocal qui ajoute des vocaux temporaires",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def add_voice_channel(self, interaction: nextcord.Interaction, category: nextcord.CategoryChannel):
        try:
            new_channel = await category.create_voice_channel(
                name=HUB_NAME
            )
            await interaction.response.send_message(f"[Vocals Cog]      "
                                                    f"Le vocal {new_channel.name} a été créé dans la catégorie {category.name}.", ephemeral=True)

        except nextcord.Forbidden:
            await interaction.response.send_message("[Vocals Cog]    Erreur:      "
                                                    "Permission insuffisantes pour créer le vocal.", ephemeral=True)

        except nextcord.NotFound:
            await interaction.response.send_message("[Vocals Cog]    Erreur:      "
                                                    "La catégorie spécifiée est introuvable.", ephemeral=True)

        except nextcord.HTTPException as e:
            await interaction.response.send_message(f"[Vocals Cog]    Erreur:      "
                                                    f"Une erreur HTTP inconnue est survenue : {e.status} - {e.text}", ephemeral=True)


    @commands.Cog.listener()
    async def on_ready(self):
        print("[Vocals Cog]    Le Cog est prêt!")

def setup(bot):
    bot.add_cog(Vocals(bot))