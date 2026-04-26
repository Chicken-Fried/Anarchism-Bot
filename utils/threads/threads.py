import nextcord
import asyncio


async def create_admin_thread(channel: nextcord.TextChannel):
    """
    Crée un thread privé et ajoute tous les membres ayant le rôle Admin.
    Note : Nécessite un Boost Niveau 2 sur le serveur.
    """
    try:
        # 1. Création du thread (Rapide)
        thread = await channel.create_thread(
            name="🔒 Staff-discussion",
            type=nextcord.ChannelType.private_thread
        )

        # 2. On récupère UNIQUEMENT les membres avec la permission admin
        # On utilise une liste de tâches pour ne pas attendre chaque membre l'un après l'autre
        admin_members = [
            member for member in channel.guild.members
            if member.guild_permissions.administrator
        ]

        if not admin_members:
            await thread.send("⚠️ Aucun administrateur trouvé pour l'ajout automatique.")
            return thread

        # 3. Utilisation de asyncio.gather pour lancer TOUTES les requêtes en même temps
        # Au lieu d'attendre le membre 1, puis le 2, puis le 3...
        # On lance toutes les demandes d'ajout simultanément.
        tasks = [thread.add_user(member) for member in admin_members]

        # return_exceptions=True permet de ne pas faire planter la boucle si un membre échoue
        await asyncio.gather(*tasks, return_exceptions=True)

        await thread.send(f"✅ Thread sécurisé créé. Accès accordé à {len(admin_members)} administrateurs.")
        return thread

    except nextcord.Forbidden:
        print("Erreur : Le bot n'a pas la permission de créer des threads privés ou de gérer les membres.")
    except Exception as e:
        print(f"Erreur lors de la création du thread : {e}")
        return None
