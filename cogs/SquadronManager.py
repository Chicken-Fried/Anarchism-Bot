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
            self.db.cleanup_old_sessions(keep_hours=12)
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

        # 2. Vérification de la condition globale "Plus de 1 heure" pour l'apparence de l'embed
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        all_old = True
        for l in lineups:
            try:
                ts = datetime.fromisoformat(l['timestamp'])
                if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
                if ts >= one_hour_ago:
                    all_old = False
                    break
            except:
                continue

        # 3. Détermination de la configuration de l'embed (Couleur et Icone globale)
        if all_old:
            display_list = [lineups[0]]
            embed_color = 0xFF0000  # Rouge
            warning_icon = "⚠️ "
        else:
            display_list = lineups[:4]  # Limite à 4 compositions
            embed_color = 0x00FF00  # Vert
            warning_icon = ""

        embed = nextcord.Embed(
            title=f"{warning_icon}Compos de/du {tag}",
            description="Compos vues dans les dernières 24 heures",
            color=embed_color
        )

        # 4. Construction des champs
        for i, lineup in enumerate(display_list, start=1):
            players = lineup.get("players", [])
            if not players:
                continue

            # --- Calcul du nombre de joueurs pour le format [X/8] ---
            num_players = len(players)

            # --- Calcul du résumé avec ORDRE STRICT (F/B/T/A) et FILTRE 0 ---
            type_counts = {}
            for p in players:
                v_type = (p.format_vehicle_mode() if hasattr(p, 'format_vehicle_mode') else (
                        p.get("vehicle_type") or "Inconnu")).upper()
                short_type = v_type[0] if v_type else "?"
                type_counts[short_type] = type_counts.get(short_type, 0) + 1

            priority_order = ['F', 'B', 'T', 'A']
            summary_parts = []
            for char in priority_order:
                count = type_counts.get(char, 0)
                if count > 0:
                    summary_parts.append(f"{count}{char}")

            if not summary_parts:
                summary_str = " / ".join([f"{c}{t}" for t, c in type_counts.items()])
            else:
                summary_str = " / ".join(summary_parts)

            # --- Calcul du temps écoulé et détection de l'âge individuel pour le bloc DIFF ---
            try:
                session_time = datetime.fromisoformat(lineup["timestamp"])
                if session_time.tzinfo is None:
                    session_time = session_time.replace(tzinfo=timezone.utc)
                diff = now - session_time
                last_seen = format_duration(diff)

                # Si cette compo précise est vieille de plus d'une heure, on prépare le préfixe rouge (-)
                diff_prefix = "- " if (session_time < one_hour_ago) else ""
            except Exception:
                last_seen = "Inconnu"
                diff_prefix = "- "

            # --- Construction de la liste des joueurs avec le préfixe DIFF ---
            player_lines = []
            for p in players:
                name = p["name"]
                v_name = p["vehicle_name"] or "Inconnu"
                formatted_line = f"{name[:15].ljust(15)} | {v_name}"
                # On ajoute le préfixe (soit "- " pour rouge, soit "" pour blanc)
                player_lines.append(f"{diff_prefix}{formatted_line}")

            player_list_str = "\n".join(player_lines)

            # --- Construction du champ final avec [X/8] ---
            field_value = (
                f"**COMPO {i} [{num_players}/8]**\n"
                f"**Vu il y a:** {last_seen}\n"
                f"**Compo:** `{summary_str}`\n"
                f"```diff\n{player_list_str}\n```"
            )
            embed.add_field(name="\u200b", value=field_value, inline=False)

        # Footer
        if all_old:
            embed.set_footer(text="Attention : Données datant de plus de 1 heure.")
        elif len(lineups) > 4:
            embed.set_footer(text=f"Affichage des 4 dernières compos sur {len(lineups)} trouvées.")

        await interaction.response.send_message(embed=embed)

    @nextcord.slash_command(
        name="comp-full",
        description="Analyse complète et audit d'une session pour un clan (Admin Only)",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def insert_composition_full(self,
                                      interaction: nextcord.Interaction,
                                      squadron_tag: str = nextcord.SlashOption(
                                          name="tag_escadron",
                                          description="Entrez le tag de l'escadron"
                                      )
                                      ):
        await interaction.response.defer(ephemeral=True)

        try:
            tag = normalize_clan_tag(squadron_tag)
            # On récupère les lineups (le plus récent est en premier grâce au tri dans la DB)
            lineups = self.db.get_lineups_for_clan(tag)

            if not lineups:
                return await interaction.response.send_message(
                    f"❌ Aucun historique trouvé pour le tag `{tag}`.",
                    ephemeral=True
                )

            # On prend la session la plus récente pour l'audit
            audit_data = lineups[0]
            players = audit_data.get("players", [])

            if not players:
                return await interaction.response.send_message("❌ Aucune donnée joueur disponible pour cette session.",
                                                               ephemeral=True)

            # --- 1. CALCUL DES STATISTIQUES DE L'ÉQUIPE ---
            total_kills = sum(p.get("kills", 0) for p in players)
            total_deaths = sum(p.get("deaths", 0) for p in players)
            team_kd = total_kills / max(1, total_deaths)

            # --- 2. IDENTIFICATION DU MVP (Le joueur avec le plus haut score) ---
            mvp_player = max(players, key=lambda x: x.get("score", 0))

            # --- 3. PRÉPARATION DES DONNÉ Renouvellement du bloc DIFF pour les joueurs ---
            # On utilise '+' pour un K/D >= 1 (Vert) et '-' pour un K/D < 1 (Rouge)
            player_stats_lines = []
            for p in players:

                le_kd = p.get("kills", 0) / max(1, p.get("deaths", 0))
                prefix = "+ " if le_kd >= 1 else "- "

                name = p["name"]
                v_name = p["vehicle_name"] or "Inconnu"
                score = p.get("score", 0)

                # Formatage : Nom | K/D | Véhicule | Score
                line = f"{prefix}{name[:12].ljust(12)} | {le_kd:.2f} | `{v_name}` | {score}pts"
                player_stats_lines.append(line)


            player_block = "\n".join(player_stats_lines)

            # --- 4. CONSTRUCTION DE L'EMBED D'AUDIT ---
            embed = nextcord.Embed(
                title=f"🔍 Audit Session: `{audit_data['timestamp'][:10]}`",
                description=f"**Map:** `{audit_data['map']}` | **Mode:** `{audit_data.get('mode', 'Realistic')}`",
                color=0x3498db  # Bleu professionnel
            )

            # Champ 1: Résultat du match
            winner_text = "Team 1" if audit_data["winner_team"] == 1 else "Team 2"
            embed.add_field(
                name="🏆 Match Result",
                value=f"**Winner:** `{winner_text}`\n**Slot:** `{audit_data['session_slot'] or 'N/A'}`",
                inline=False
            )

            # Champ 2: Performance Individuelle (Le bloc de code coloré)
            embed.add_field(
                name="⚔️ Player Breakdown (K/D $\ge$ 1 in Green)",
                value=f"```diff\n{player_block}\n```",
                inline=False
            )

            # Champ 3: Statistiques Globales de l'équipe
            embed.add_field(
                name="📊 Team Analytics",
                value=(
                    f"**Total Kills:** `{total_kills}`\n"
                    f"**Team K/D Ratio:** `{team_kd:.2f}`\n"
                    f"**MVP:** 👑 **{mvp_player['name']}**"
                ),
                inline=False
            )

            # Footer avec info de la session
            embed.set_footer(text=f"Session ID: {audit_data['session_id']} | Audit réalisé par {interaction.user.name}")

            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de l'audit : {e}")


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