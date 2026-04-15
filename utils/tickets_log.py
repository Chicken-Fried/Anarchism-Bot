import os
import json
import nextcord

async def save_channel_to_json(channel: nextcord.TextChannel)-> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, ".."))

    log_dir = os.path.join(project_root, "logs")
    file_path = os.path.join(log_dir, f"{channel.id}.json")


    try:
        os.makedirs("logs", exist_ok=True)
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

        print(f"[Tickets Utils]   Enregistrement du ticket | {channel.name}")

        return file_path

    except Exception as e:
        print(f"[Tickets Utils]   Erreur lors de l'exécution de la fonction save_channel_to_json | {e}")
        print(f"[DEBUG]  Chemin tenté : {file_path}")

        return None