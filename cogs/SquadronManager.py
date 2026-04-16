import nextcord
import logging
import os

from datetime import datetime, timezone, timedelta, time
from wrpl.all_units import build
from pathlib import Path

from wrpl.db_replay import normalize_clan_tag
from helpers.helpers import format_duration

from nextcord.ext import commands, tasks
log = logging.getLogger(__name__)

ENV_DB_PATH = os.getenv("DATABASE_UNITS", "database/all_units.json")
UNITS_DB    = os.path.abspath(ENV_DB_PATH)

class SquadronManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.units_db = UNITS_DB
        self.db = bot.db_replays
        self.daily_cleanup_db.start()
        self.daily_check_api.start()

    def cog_unload(self):
        self.daily_cleanup_db.cancel()
        self.daily_check_api.cancel()

    @tasks.loop(time=time(hour=0, minute=30))
    async def daily_cleanup_db(self):
        """
        S'exécute tous les jours à 00:30 précise pour nettoyer la base et les fichiers.
        :return:
        """
        print("[SquadronManager Cog]     Automatisation lancée !")
        try:
            # On appelle la méthode de nettoyage avec un délai de 24h
            self.db.cleanup_old_sessions(keep_hours=24)
            print("[SquadronManager Cog]     Automatisation terminée !")
        except Exception as e:
            print("[SquadronManager Cog]     Erreurr - Erreur lors de l'automatisation: %s", e)
            log.error("Erreur lors de l'exécution de daily_task : %s", e)

    @tasks.loop(time=time(hour=14, minute=00))
    async def daily_check_api(self):
        """
        S'exécute tous les jours à 14:00 pour mettre à jour all_units.json.
        :return:
        """
        print("[SquadronManager Cog]     Checking de l'API-Thunderskills lancée !")
        try:
            output_path = Path(self.units_db)

            print("[SquadronManager Cog]     Mise à jour de all_units.json...")

            build(
                output=output_path,
                use_fallback=True,  # Equivalent to default
                download_images=True,  # Set to False if you don't want downloads every day
                skip_existing_images=True,
                verbose=True
            )

            print("[SquadronManager Cog]     Mise à jour de all_units.json complète")

        except Exception as e:
            print("[SquadronManager Cog]     Erreurr - Erreur lors de la mise à jour de all_units.json: %s", e)
            log.error("Erreur lors de l'exécution de daily_task : %s", e)

    """@nextcord.slash_command(
        name="comp-lite",
        description="Retourne la line-up d'une team"
    )
    async def insert_composition_lite(self,
                                      interaction: nextcord.Interaction,
                                      squadron_tag: str = nextcord.SlashOption(
                                          name="tag_escadron",
                                          description="Entrez le tag de l'escadron"
                                      )
                                      ):
        tag = normalize_clan_tag(squadron_tag)
        lineups = self.db.get_lineups_for_clan(tag)

        if not lineups:
            return await interaction.response.send_message(
                f"❌ Aucune composition trouvée pour le tag `{tag}`.",
                ephemeral=True
            )

        embed = nextcord.Embed(
            title=f"Comps for {tag}",
            description="Comps seen in the last 24 hours",
            color=0x2f3136
        )

        for i, lineup in enumerate(lineups, start=1):
            players = lineup.get("players", [])
            if not players:
                continue

            # 1. Calcul du résumé (ex: 4F / 1T)
            type_counts = {}
            for p in players:
                v_type = (p.get("vehicle_type") or "Unknown").upper()
                short_type = v_type[0] if v_type else "?"
                type_counts[short_type] = type_counts.get(short_type, 0) + 1

            summary_str = " / ".join([f"{count}{t}" for t, count in type_counts.items()])

            # 2. Construction de la liste des joueurs avec ALIGNEMENT
            player_lines = []
            for p in players:
                name = p["name"]
                v_name = p["vehicle_name"] or "Unknown"

                # On limite le nom à 15 caractères et on complète avec des espaces
                # pour que le "|" soit toujours au même endroit.
                # Ajustez le chiffre '15' selon la longueur max de vos pseudos.
                formatted_line = f"{name[:15].ljust(15)} | {v_name}"
                player_lines.append(formatted_line)

            player_list_str = "\n".join(player_lines)

            # 3. Calcul du temps écoulé (Last seen)
            try:
                session_time = datetime.fromisoformat(lineup["timestamp"])
                # Assurez-vous que session_time est en UTC pour la comparaison
                if session_time.tzinfo is None:
                    session_time = session_time.replace(tzinfo=timezone.utc)

                diff = datetime.now(timezone.utc) - session_time
                last_seen = format_duration(diff)
            except Exception:
                last_seen = "Unknown"

            # 4. Construction du champ (Field)
            field_value = (
                f"**COMP {i}**\n"
                f"**Last seen:** {last_seen}\n"
                f"**Comp:** `{summary_str}`\n"
                f"```\n{player_list_str}\n```"
            )

            embed.add_field(name="\u200b", value=field_value, inline=False)

        await interaction.response.send_message(embed=embed)"""

    @nextcord.slash_command(
        name="comp-lite",
        description="Retourne la line-up d'une team"
    )
    async def insert_composition_lite(self,
                                      interaction: nextcord.Interaction,
                                      squadron_tag: str = nextcord.SlashOption(
                                          name="tag_escadron",
                                          description="Entrez le tag de l'escadron"
                                      )
                                      ):
        tag = normalize_clan_tag(squadron_tag)
        lineups = self.db.get_lineups_for_clan(tag)

        if not lineups:
            return await interaction.response.send_message(
                f"❌ Aucune composition trouvée pour le tag `{tag}`.",
                ephemeral=True
            )

        # 1. Trier les lineups par date (du plus récent au plus ancien)
        lineups.sort(key=lambda x: x['timestamp'], reverse=True)

        # 2. Vérification de la condition "Plus de 2 heures"
        now = datetime.now(timezone.utc)
        two_hours_ago = now - timedelta(hours=2)

        all_old = True
        for l in lineups:
            try:
                ts = datetime.fromisoformat(l['timestamp'])
                if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
                if ts >= two_hours_ago:
                    all_old = False  # On a trouvé au moins une comp récente
                    break
            except:
                continue

        # 3. Détermination de la configuration de l'embed (Couleur, Liste, Icone)
        if all_old:
            # Cas : Uniquement des données vieilles de plus de 2h
            display_list = [lineups[0]]  # On n'affiche que la plus récente
            embed_color = 0xFF0000  # Rouge
            warning_icon = "⚠️ "
        else:
            # Cas : Données récentes présentes
            display_list = lineups[:10]  # Limite à 10 compositions
            embed_color = 0x00FF00  # Vert
            warning_icon = ""

        embed = nextcord.Embed(
            title=f"{warning_icon}Comps for {tag}",
            description="Comps seen in the last 24 hours",
            color=embed_color
        )

        # 4. Construction des champs pour la liste sélectionnée (display_list)
        for i, lineup in enumerate(display_list, start=1):
            players = lineup.get("players", [])
            if not players:
                continue

            # Calcul du résumé (ex: 4F / 1T)
            type_counts = {}
            for p in players:
                v_type = (p.format_vehicle_type() if hasattr(p, 'format_vehicle_type') else (
                            p.get("vehicle_type") or "Unknown")).upper()
                short_type = v_type[0] if v_type else "?"
                type_counts[short_type] = type_counts.get(short_type, 0) + 1
            summary_str = " / ".join([f"{count}{t}" for t, count in type_counts.items()])

            # Construction de la liste des joueurs
            player_lines = []
            for p in players:
                name = p["name"]
                v_name = p["vehicle_name"] or "Unknown"
                formatted_line = f"{name[:15].ljust(15)} | {v_name}"
                player_lines.append(formatted_line)
            player_list_str = "\n".join(player_lines)

            # Calcul du temps écoulé
            try:
                session_time = datetime.fromisoformat(lineup["timestamp"])
                if session_time.tzinfo is None:
                    session_time = session_time.replace(tzinfo=timezone.utc)
                diff = now - session_time
                last_seen = format_duration(diff)
            except Exception:
                last_seen = "Unknown"

            # Construction du champ (Field)
            field_value = (
                f"**COMP {i}**\n"
                f"**Last seen:** {last_seen}\n"
                f"**Comp:** `{summary_str}`\n"
                f"```\n{player_list_str}\n```"
            )

            embed.add_field(name="\u200b", value=field_value, inline=False)

        # Footer pour info supplémentaire si nécessaire
        if all_old:
            embed.set_footer(text="Attention : Données datant de plus de 2 heures.")
        elif len(lineups) > 10:
            embed.set_footer(text=f"Affichage des 10 dernières compos sur {len(lineups)} trouvées.")

        await interaction.response.send_message(embed=embed)


    @nextcord.slash_command(
        name="comp-full",
        description="Retourne la line-up complète d'une team",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def insert_composition_full(self,
                                      interaction: nextcord.Interaction,
                                      squadron_tag: str = nextcord.SlashOption(
                                            name="tag_escadron",
                                            description="Entrez le tag de l'escadron, en minuscule ou en majuscule"
                                      )
    ):
        return

    @nextcord.slash_command(
        name="log-squadron",
        description="Retourne les logs d'un escadron",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def logs_squadron(self,
                            interaction: nextcord.Interaction,
                            squadron_tag: str = nextcord.SlashOption(
                                name="tag_escadron",
                                description="Entrez le tag de l'escadron, en minuscule ou en majuscule"
                            ),
                            log_type: str = nextcord.SlashOption(
                                name="type_log",
                                description="Le type de logs [Logs, Points, Leaderboards, Both (Logs+Points)]",
                                choices=["logs", "points", "leaderboards", "both"]
                            )
    ):
        return

    @commands.Cog.listener()
    async def on_ready(self):
        print("[SquadronManager Cog]   Le Cog est prêt!")


def setup(bot):
    bot.add_cog(SquadronManager(bot))