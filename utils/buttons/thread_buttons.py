import nextcord

class UrlGoogleSheetApplicationButton(nextcord.ui.Button):

    def __init__(self):
        super().__init__(label="Voir les candidatures", style=nextcord.ButtonStyle.green, custom_id="url_application_gs_admin")

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        is_admin = user.guild_permissions.administrator

        if is_admin:
            url = "https://docs.google.com/spreadsheets/d/1DodycLQR8zrrZlz85yEfWlku4-iyc-f9Qfkxs4yror0/edit?resourcekey=&gid=763109175#gid=763109175"
            await interaction.followup.send(
                content=f"✅ **Accès Autorisé.** Voici le lien : [Cliquez ici]({url})",
                ephemeral=True
            )
            print(f"[Thread Views]   Ouverture du lien URL => Par l'utilisateur | Accès autorisé : {user.name} est admin.")

        else:
            # --- LOGIQUE POUR LES NON-ADMINS ---
            print(f"[Thread Views]   Ouverture du lien URL => Par l'utilisateur | Accès refusé : {user.name} n'est pas admin.")

            await interaction.followup.send(
                content="❌ **Accès Refusé.** Vous devez être administrateur pour voir ce lien.",
                ephemeral=True
            )