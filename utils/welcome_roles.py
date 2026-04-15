import os
import json
import nextcord
import asyncio

from .models.roles_config import RoleWelcome

file_lock = asyncio.Lock()

async def save_roles_list_to_json(roles: list[nextcord.Role])-> str | None:
    """
    Ecrit sur un json les roles existant issu de la guild escadron
    :param roles: liste des roles à sauvegarder
    :return:
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, ".."))

    log_dir = os.path.join(project_root, "data")
    file_path = os.path.join(log_dir, f"roles_guild_sqb.json")


    try:
        async with file_lock:
            os.makedirs(log_dir, exist_ok=True)
            roles_data = []

            for role in roles:
                if not role:
                    continue

                roles_data.append(
                    [
                        role.id,
                        role.name
                    ]
                )

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(roles_data, f, indent=4, ensure_ascii=False)

            print(f"[Welcome Utils]   Enregistrement des roles de la guild")

            return file_path

    except Exception as e:
        print(f"[Welcome Utils]   Erreur lors de l'exécution de la fonction save_roles_list_to_json | {e}")
        print(f"[DEBUG]  Chemin tenté : {file_path}")

        return None

async def open_roles_list_json()-> list[RoleWelcome] | None:
    """
    Ouvre le fichier json si existant et retourne les informations des rôles de la guild sous
    la forme de liste de class RoleWelcome
    :return:
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, ".."))

    log_dir = os.path.join(project_root, "data")
    file_path = os.path.join(log_dir, f"roles_guild_sqb.json")

    try:
        async with file_lock:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

                result = []

                for role in data:
                    obj = RoleWelcome(name=role[1], id=role[0])
                    result.append(obj)

                return result


    except Exception as e:
        print(f"[Welcome Utils]   Erreur lors de l'exécution de la fonction open_roles_list_json | {e}")
        print(f"[DEBUG]  Chemin tenté : {file_path}")

        return None