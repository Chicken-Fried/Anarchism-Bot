import nextcord


async def create_admin_thread(channel: nextcord.TextChannel):
    """
    Crée un thread privé et ajoute tous les membres ayant le rôle Admin.
    Note : Nécessite un Boost Niveau 2 sur le serveur.
    """
    try:
        # 1. Création du thread privé
        thread = await channel.create_thread(
            name="🔒 Staff-discussion",
            type=nextcord.ChannelType.private_thread
        )

        # 2. Trouver tous les membres qui ont la permission 'administrator'
        # On parcourt les membres du serveur (guild)
        admin_members = [
            member for member in channel.guild.members
            if member.guild_permissions.administrator
        ]

        # 3. Ajouter chaque membre trouvé au thread
        for member in admin_members:
            try:
                await thread.add_user(member)
            except nextcord.Forbidden:
                continue
            except Exception:
                continue

        # 4. Message de confirmation
        await thread.send("✅ Thread sécurisé créé. Accès accordé aux administrateurs du serveur.")

        return thread

    except nextcord.Forbidden:
        print("Erreur : Le bot n'a pas la permission de créer des threads privés ou de gérer les membres.")
    except Exception as e:
        print(f"Erreur lors de la création du thread : {e}")
        return None
