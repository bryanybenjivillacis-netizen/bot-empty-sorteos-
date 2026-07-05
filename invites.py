"""
invites.py — Tracking de invitaciones con slash commands.

Comandos:
  /setinvite channel  #canal
  /setinvite threshold <n> [recompensa]
  /setinvite altdays  <1-7>
  /invites   [@user]
  /invitetop
  /resetinvites
"""

import discord
from discord import app_commands
from discord.ext import commands
from config import db
import logging
from datetime import timezone

log = logging.getLogger("bot.invites")

_invite_cache: dict[int, dict[str, int]] = {}


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_config(guild_id: int) -> dict:
    config = db.get_guild(guild_id)
    return config.get("invites", {
        "channel_id": None,
        "threshold": 5,
        "altdays": 3,
        "reward": "",
        "counts": {},
        "milestones": {},
        "invited_by": {},
    })


def _save_config(guild_id: int, cfg: dict):
    config = db.get_guild(guild_id)
    config["invites"] = cfg
    db.update_guild(guild_id, config)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_alt(member: discord.Member, altdays: int) -> bool:
    age = (discord.utils.utcnow() - member.created_at.replace(tzinfo=timezone.utc)).days
    return age < altdays


def _build_milestone_embed(inviter: discord.Member, count: int,
                            reward: str, invited_ids: list) -> discord.Embed:
    embed = discord.Embed(
        description=f"{inviter.mention} consiguió invitar **{count} personas** al servidor 🎉",
        color=0x2b2d31,
    )
    if reward:
        embed.add_field(name="Recompensa", value=reward, inline=False)
    if invited_ids:
        mentions = " ".join(f"<@{uid}>" for uid in invited_ids[-count:])
        embed.add_field(name="Personas invitadas", value=mentions, inline=False)
    embed.set_thumbnail(url=inviter.display_avatar.url)
    embed.set_footer(text=inviter.guild.name)
    return embed


# ── Grupo /setinvite ──────────────────────────────────────────────────────────

class SetinviteGroup(app_commands.Group, name="setinvite", description="Configuración de invitaciones"):

    @app_commands.command(name="channel", description="Canal de notificaciones de milestone")
    @app_commands.describe(canal="Canal de texto")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        cfg = _get_config(interaction.guild.id)
        cfg["channel_id"] = canal.id
        _save_config(interaction.guild.id, cfg)
        await interaction.response.send_message(
            embed=discord.Embed(description=f"Canal configurado: {canal.mention}", color=0x57f287),
            ephemeral=True,
        )

    @app_commands.command(name="threshold", description="Milestone de invitaciones y recompensa")
    @app_commands.describe(
        numero="Cada cuántas invitaciones notifica",
        recompensa="Texto de recompensa (opcional)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def threshold(self, interaction: discord.Interaction, numero: int, recompensa: str = ""):
        if numero < 1:
            return await interaction.response.send_message(
                "El umbral debe ser al menos `1`.", ephemeral=True
            )
        cfg = _get_config(interaction.guild.id)
        cfg["threshold"] = numero
        cfg["reward"] = recompensa.strip()
        _save_config(interaction.guild.id, cfg)
        desc = f"Notificación cada `{numero}` invitaciones."
        if recompensa:
            desc += "\nRecompensa: " + recompensa.strip()
        await interaction.response.send_message(
            embed=discord.Embed(description=desc, color=0x57f287),
            ephemeral=True,
        )

    @app_commands.command(name="altdays", description="Días mínimos de cuenta para no ser alt")
    @app_commands.describe(dias="Entre 1 y 7")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def altdays(self, interaction: discord.Interaction, dias: int):
        if dias < 1 or dias > 7:
            return await interaction.response.send_message(
                "El valor debe estar entre `1` y `7`.", ephemeral=True
            )
        cfg = _get_config(interaction.guild.id)
        cfg["altdays"] = dias
        _save_config(interaction.guild.id, cfg)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"Cuentas menores a `{dias}` días serán ignoradas.",
                color=0x57f287,
            ),
            ephemeral=True,
        )


# ── Cog ──────────────────────────────────────────────────────────────────────

class Invites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try:
                invites = await guild.fetch_invites()
                _invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        try:
            invites = await guild.fetch_invites()
            _invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        guild = member.guild
        cfg = _get_config(guild.id)

        try:
            new_invites = await guild.fetch_invites()
        except Exception:
            return

        old_cache = _invite_cache.get(guild.id, {})
        inviter = None
        for inv in new_invites:
            if inv.uses > old_cache.get(inv.code, 0):
                inviter = inv.inviter
                break

        _invite_cache[guild.id] = {inv.code: inv.uses for inv in new_invites}

        if not inviter or inviter.bot:
            return

        if _is_alt(member, cfg.get("altdays", 3)):
            return

        uid = str(inviter.id)
        counts = cfg.get("counts", {})
        counts[uid] = counts.get(uid, 0) + 1
        cfg["counts"] = counts

        invited_by = cfg.get("invited_by", {})
        invited_by.setdefault(uid, [])
        if member.id not in invited_by[uid]:
            invited_by[uid].append(member.id)
        cfg["invited_by"] = invited_by

        threshold = cfg.get("threshold", 5)
        channel_id = cfg.get("channel_id")
        count = counts[uid]
        milestones = cfg.get("milestones", {})
        last_milestone = milestones.get(uid, 0)
        current_milestone = (count // threshold) * threshold

        if current_milestone > last_milestone and current_milestone > 0:
            milestones[uid] = current_milestone
            cfg["milestones"] = milestones

        # Una sola escritura al final
        _save_config(guild.id, cfg)
        log.info(f"[{guild.name}] {inviter} ahora tiene {count} invitaciones")

        if not channel_id or not (current_milestone > last_milestone and current_milestone > 0):
            return

        channel = guild.get_channel(int(channel_id))
        inviter_member = guild.get_member(inviter.id)
        if channel and inviter_member:
            try:
                reward = cfg.get("reward", "")
                invited_ids = cfg.get("invited_by", {}).get(uid, [])
                await channel.send(embed=_build_milestone_embed(
                    inviter_member, current_milestone, reward, invited_ids
                ))
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        _invite_cache.setdefault(invite.guild.id, {})[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        _invite_cache.get(invite.guild.id, {}).pop(invite.code, None)

    @app_commands.command(name="invites", description="Ver cuántas invitaciones tiene alguien")
    @app_commands.describe(usuario="Usuario a consultar (vacío = tú)")
    async def invites_cmd(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer(ephemeral=True)
        target = usuario or interaction.user
        cfg = _get_config(interaction.guild.id)
        count = cfg.get("counts", {}).get(str(target.id), 0)
        await interaction.followup.send(
            embed=discord.Embed(
                description=f"{target.mention} tiene **{count}** invitaciones.",
                color=0x2b2d31,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="invitetop", description="Top 5 usuarios con más invitaciones")
    async def invitetop(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = _get_config(interaction.guild.id)
        counts = cfg.get("counts", {})
        if not counts:
            return await interaction.followup.send("No hay datos aún.", ephemeral=True)
        sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        lines = []
        for i, (uid, count) in enumerate(sorted_counts):
            member = interaction.guild.get_member(int(uid))
            name = member.mention if member else f"`{uid}`"
            lines.append(f"{medals[i]} {name} — **{count}** invitaciones")
        await interaction.followup.send(
            embed=discord.Embed(title="Top 5 Inviters", description="\n".join(lines), color=0x2b2d31),
            ephemeral=True,
        )

    @app_commands.command(name="resetinvites", description="Reinicia todas las estadísticas de invitaciones")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def resetinvites(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = _get_config(interaction.guild.id)
        cfg["counts"] = {}
        cfg["milestones"] = {}
        cfg["invited_by"] = {}
        _save_config(interaction.guild.id, cfg)
        await interaction.followup.send(
            embed=discord.Embed(description="Estadísticas reiniciadas.", color=0xed4245),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Invites(bot))
    bot.tree.add_command(SetinviteGroup())
