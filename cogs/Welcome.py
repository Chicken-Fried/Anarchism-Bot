import nextcord
import os
import io
import aiohttp

from images.welcome.welcome_image import generate_welcome_image
from utils.welcome_roles import save_roles_list_to_json, open_roles_list_json, RoleWelcome
from nextcord.ext import commands

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.roles = [
            int(os.getenv("GUILD_SQB_ROLE_ID_DEFAULT")),
            int(os.getenv("GUILD_SQB_ROLE_ID_WARN")),
            int(os.getenv("GUILD_SQB_ROLE_ID_POP")),
            int(os.getenv("GUILD_SQB_ROLE_ID_GRADES")),
            int(os.getenv("GUILD_SQB_ROLE_ID_ROLES")),
            int(os.getenv("GUILD_SQB_ROLE_ID_LOCALISATION"))
        ]

        self.guild_id = int(os.getenv("GUILD_SQB_SERVER_ID"))
        self.welcome_channel_id = int(os.getenv("GUILD_SQB_WELCOME_CHANNEL_ID"))

        self.bg_path = "images/welcome/welcome_image.jpg"
        self.logo_path = "images/logo/python_logo.png"
        self.font_path = "utils/fonts/JosefinSans-Regular.ttf"

    """@commands.Cog.listener()
    async def on_member_join(self, member: nextcord.Member):
        # Vérification que l'événement se produit sur le bon serveur
        print(f"[Welcome Cog]      : {member} a rejoint le serveur {member.guild}")

        if member.guild.id != self.guild_id:
            return

        # 1. Attribution du rôle
        role = member.guild.get_role(self.role_id)
        if role:
            try:
                await member.add_roles(role)
            except nextcord.Forbidden:
                print(f"[Error] Permissions insuffisantes pour donner le rôle à {member.name}")

        # 2. Envoi du message de bienvenue
        channel = member.guild.get_channel(self.welcome_channel_id)
        if not channel:
            return

        # Création de l'Embed style "Liquidglass"
        # Note : La couleur 0x2b2d31 simule le mode sombre de Discord pour l'effet de fusion
        embed = nextcord.Embed(
            title="Ho ! Un nouveau membre !",
            description=(
                f"👋 Bienvenue {member.mention} sur **{member.guild.name}** !\n"
                f"Ravi de t'avoir parmi les {member.guild.member_count} membres 🎉\n"
                f"Tu nous rejoins le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — installe-toi bien 😆\n\n"
                f"👉 Passe dire bonjour et fais connaissance avec tout le monde ! 💬"
            ),
            color=0x2b2d31
        )

        # Pour l'effet visuel iOS26/Liquidglass, il est crucial d'utiliser une image
        # de bannière stylisée (que tu peux créer sur Canva ou Photoshop)
        # Remplace l'URL ci-dessous par ton lien d'image personnalisé
        embed.set_image(url="https://cdn.pixabay.com/photo/2017/07/26/02/30/alpha-2540240_1280.jpg")

        # Optionnel : Ajouter l'avatar de l'utilisateur dans un petit cercle
        embed.set_thumbnail(url=member.display_avatar.url)

        await channel.send(embed=embed)"""


    @commands.Cog.listener()
    async def on_guild_role_create(self, role: nextcord.Role):
        """Déclenché quand un nouveau rôle est créé"""
        # On vérifie si le rôle appartient bien à notre guilde cible
        if role.guild.id == self.guild_id:
            print(f"[Welcome Cog]    Nouveau rôle détecté : {role.name}. Mise à jour du JSON...")
            await self.update_roles_file()


    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: nextcord.Role):
        """Déclenché quand un rôle est supprimé"""
        if role.guild.id == self.guild_id:
            print(f"[Welcome Cog]    Rôle supprimé : {role.name}. Mise à jour du JSON...")
            await self.update_roles_file()


    async def update_roles_file(self):
        """Méthode interne pour rafraîchir le fichier JSON avec les rôles actuels"""
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return

        # On récupère la liste des rôles que vous suivez (ceux stockés dans self.roles)
        roles_to_save = []
        for role_id in self.roles:
            existing_role = guild.get_role(role_id)
            if existing_role:
                roles_to_save.append(existing_role)

        await save_roles_list_to_json(roles_to_save)


    @commands.Cog.listener()
    async def on_member_join(self, member: nextcord.Member):
        if member.guild.id != self.guild_id:
            return

        print(f"[Welcome Cog] : {member} a rejoint le serveur {member.guild}")

        # 1. Attribution du rôle
        roles = await open_roles_list_json()
        guild = member.guild

        if roles:
            try:
                for r in roles:
                    role = guild.get_role(r.id)
                    await member.add_roles(role)
                    print(f"[Welcome Cog]     "
                          f"Le rôle {role.name} a été ajouté à l'utilisateur - {member.name}")

            except nextcord.Forbidden:
                print(f"[Welcome Cog]     "
                      f"Erreur - Permissions insuffisantes pour {member.name}")

        # 2. Préparation de l'image personnalisée
        channel = member.guild.get_channel(self.welcome_channel_id)
        if not channel:
            return

        try:
            # On télécharge l'avatar du membre en mémoire (BytesIO)
            async with aiohttp.ClientSession() as session:
                async with session.get(member.display_avatar.url) as resp:
                    if resp.status != 200:
                        raise Exception("Impossible de télécharger l'avatar")
                    avatar_bytes = io.BytesIO(await resp.read())
                    # On utilise un objet Image de Pillow pour que la fonction puisse le lire
                    from PIL import Image
                    avatar_bytes.name = "avatar.png"

                    # Génération de l'image (on passe l'objet BytesIO comme si c'était un chemin)
            # Note: Dans ta fonction, il faudra adapter pour accepter des objets BytesIO ou charger via URL
            img_buffer = generate_welcome_image(
                user_avatar_url=avatar_bytes,
                server_logo_path=self.logo_path,
                user_name=str(member.name),
                background_path=self.bg_path,
                font_path=self.font_path
            )

            # Envoi de l'image générée
            file = nextcord.File(img_buffer, filename="welcome.png")

            embed = nextcord.Embed(
                title=f"Bienvenue dans les Quartiers Généraux de l'Empire Galactique !",
                description=f"{member.mention}, nous sommes ravis de t'accueillir parmi nous ! 🎉\n\n"
                            f"Prends le temps de te présenter et de découvrir les différents salons du serveur.\n\n"
                            f"Si tu as des questions, n'hésite pas à demander de l'aide à notre équipe ou à la communauté !",
                color=0x2b2d31
            )

            embed.set_image(url="attachment://welcome.png")

            await channel.send(
                embed=embed,
                file=file
            )

        except Exception as e:
            print(f"[Error Welcome Image] : {e}")
            # Fallback : Envoi d'un embed classique si la génération échoue
            embed = nextcord.Embed(
                title="Bienvenue !",
                description=f"Bienvenue dans l'Empire Galactique - {member.mention} !"
            )
            await channel.send(embed=embed)


    @commands.Cog.listener()
    async def on_ready(self):
        print("[Welcome Cog]   Le Cog est prêt!")
        guild = self.bot.get_guild(self.guild_id)

        roles = []

        for role in self.roles:
            exist = guild.get_role(role)
            if not exist:
                continue
            roles.append(exist)

        await save_roles_list_to_json(roles)




def setup(bot):
    bot.add_cog(Welcome(bot))