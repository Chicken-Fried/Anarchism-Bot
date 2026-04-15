import os
import json
import nextcord

from dotenv import load_dotenv
load_dotenv()

async def save_channel_to_json(channel: nextcord.TextChannel)-> str | None:
    log_dir_name = os.getenv("DATABASE_LOGS", "logs")

    # 2. Construire le chemin absolu vers le dossier logs du projet
    # On part de la racine du projet pour être sûr d'être dans le volume Docker
    project_root = os.path.abspath(os.path.join(os.getcwd(), ".."))  # Ajuste selon l'emplacement de ton script
    # Mieux encore : si ton script est lancé depuis /app, utilise simplement :
    log_dir_path = os.path.join(os.getcwd(), log_dir_name)

    file_path = os.path.join(log_dir_path, f"{channel.id}.json")

    try:
        # 3. Créer le dossier de destination s'il n'existe pas (très important pour Docker)
        os.makedirs(log_dir_path, exist_ok=True)

        messages_data = []

        async for message in channel.history(limit=None, oldest_first=True):
            messages_data.append({
                "author": str(message.author),
                "author_id": message.author.id,
                "content": message.content,
                "embeds": [embed.to_dict() for embed in message.embeds],
                "reactions": [str(r.emoji) for r in message.reactions],
                "created_at": message.created_at.isoformat(),
                "attachments": [att.url for att in message.attachments]
            })

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(messages_data, f, indent=4, ensure_ascii=False)

        print(f"[Tickets Utils]   Enregistrement du ticket | {channel.name} -> {file_path}")
        return file_path

    except Exception as e:
        print(f"[Tickets Utils]   Erreur lors de l'exécution de la fonction save_channel_to_json | {e}")
        print(f"[DEBUG]  Chemin tenté : {file_path}")
        return None