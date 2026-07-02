"""
giveaway.py — Giveaways con slash commands y Modal.

Comandos:
  /gcreate                  — abre Modal (Premio, Duración, Canal)
  /gend    <message_id>     — termina giveaway antes de tiempo
  /greroll <message_id>     — rerollea ganador
  /gbonus add @user %       — da bonus de probabilidad
  /gbonus remove @user      — quita bonus
  /gbonus list              — lista bonus activos
"""

import discord
from discord import app_commands
from discord.ext import commands
from config import db
import logging
import random
import asyncio
from datetime import datetime, timezone, timedelta

log = logging.getLogger("bot.giveaway")
GIVEAWAY_EMOJI = "🎉"


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_giveaways(guild_id: int) -> dict:
    config = db.get_guild(guild_id)
    return config.get("giveaways", {})


def _save_giveaways(guild_id: int, data: dict):
    config = db.get_guild(guild_id)
    config["giveaways"] = data
    db.update_guild(guild_id, config)


def _get_bonuses(guild_id: int) -> dict:
    config = db.get_guild(guild_id)
    return config.get("giveaway_bonuses", {})


def _save_bonuses(guild_id: int, data: dict):
    config = db.get_guild(guild_id)
    config["giveaway_bonuses"] = data
    db.update_guild(guild_id, config)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_duration(text: str) -> int | None:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    text = text.strip().lower()
    if len(text) > 1 and text[-1] in units and text[:-1].isdigit():
        return int(text[:-1]) * units[text[-1]]
    if text.isdigit():
        return int(text)
    return None


def _pick_winner(participants: list, bonuses: dict) -> int | None:
    if not participants:
        return None
    pool = []
    for uid in participants:
        tickets = 100 + bonuses.get(str(uid), 0)
        pool.extend([uid] * tickets)
    return random.choice(pool)


def _build_embed(prize: str, end_time: datetime, participants: int = 0,
                 ended: bool = False, winner_id: int = None) -> discord.Embed:
    embed = discord.Embed(color=0x2b2d31)
    embed.title = f"{GIVEAWAY_EMOJI} {prize}"
    if ended:
        embed.description = f"**Ganador:** <@{winner_id}>" if winner_id else "Sin participantes."
        embed.set_footer(text="Giveaway terminado")
    else:
        ts = int(end_time.timestamp())
        embed.description = f"Termina: <t:{ts}:R>"
        embed.add_field(name="Participantes", value=str(participants))
        embed.set_footer(text=f"Termina {end_time.strftime('%d/%m/%Y %H:%M')} UTC")
    return embed


# ── Modal ─────────────────────────────────────────────────────────────────────

class GiveawayModal(discord.ui.Modal, title="Crear Giveaway"):
    prize = discord.ui.TextInput(
        label="Premio",
        placeholder="Ej: Nitro, Rol VIP, $10 Steam...",
        max_length=100,
    )
    duration = discord.ui.TextInput(
        label="Duración",
        placeholder="Ej: 10m, 2h, 1d",
        max_length=10,
    )
    channel_name = discord.ui.TextInput(
        label="Canal (nombre exacto)",
        placeholder="Ej: giveaways",
        max_length=100,
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        seconds = _parse_duration(self.duration.value)
        if not seconds or seconds < 10:
            return await interaction.response.send_message(
                "Duración inválida. Usa `10m`, `2h`, `1d`. Mínimo 10 segundos.",
                ephemeral=True,
            )

        channel = discord.utils.get(
            interaction.guild.text_channels,
            name=self.channel_name.value.strip()
        )
        if not channel:
            return await interaction.response.send_message(
                f"No encontré el canal `{self.channel_name.value}`. Verifica el nombre exacto.",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)

        end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        embed = _build_embed(self.prize.value, end_time, participants=0)
        msg = await channel.send(embed=embed)

        view = JoinView(self.cog, interaction.guild.id, msg.id)
        await msg.edit(view=view)

        giveaways = _get_giveaways(interaction.guild.id)
        giveaways[str(msg.id)] = {
            "channel_id": channel.id,
            "prize": self.prize.value,
            "end_time": end_time.isoformat(),
            "ended": False,
            "winner_id": None,
            "participants": [],
        }
        _save_giveaways(interaction.guild.id, giveaways)

        task = asyncio.create_task(
            self.cog._wait_and_end(interaction.guild.id, msg.id, seconds)
        )
        self.cog._tasks[str(msg.id)] = task

        await interaction.followup.send(
            f"Giveaway creado en {channel.mention}. ID: `{msg.id}`",
            ephemeral=True,
        )


# ── Botón participar ──────────────────────────────────────────────────────────

class JoinView(discord.ui.View):
    def __init__(self, cog, guild_id: int, message_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.message_id = message_id

    @discord.ui.button(label="🎉 Participar", style=discord.ButtonStyle.primary,
                       custom_id="giveaway_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaways = _get_giveaways(self.guild_id)
        data = giveaways.get(str(self.message_id))

        if not data or data.get("ended"):
            return await interaction.response.send_message(
                "Este giveaway ya terminó.", ephemeral=True
            )

        uid = interaction.user.id
        participants = data.get("participants", [])

        if uid in participants:
            participants.remove(uid)
            msg = "Saliste del giveaway."
        else:
            participants.append(uid)
            msg = "¡Entraste al giveaway! 🎉"

        data["participants"] = participants
        giveaways[str(self.message_id)] = data
        _save_giveaways(self.guild_id, giveaways)

        end_time = datetime.fromisoformat(data["end_time"])
        embed = _build_embed(data["prize"], end_time, participants=len(participants))
        await interaction.response.edit_message(embed=embed)
        await interaction.followup.send(msg, ephemeral=True)


# ── Grupo /gbonus ─────────────────────────────────────────────────────────────

class GbonusGroup(app_commands.Group, name="gbonus", description="Gestión de bonus en giveaways"):

    @app_commands.command(name="add", description="Da bonus de probabilidad a un usuario")
    @app_commands.describe(usuario="Usuario", porcentaje="Bonus entre 3 y 50")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add(self, interaction: discord.Interaction, usuario: discord.Member, porcentaje: int):
        if porcentaje < 3 or porcentaje > 50:
            return await interaction.response.send_message(
                "El bonus debe estar entre `3%` y `50%`.", ephemeral=True
            )
        bonuses = _get_bonuses(interaction.guild.id)
        bonuses[str(usuario.id)] = porcentaje
        _save_bonuses(interaction.guild.id, bonuses)
        await interaction.response.send_message(
            f"{usuario.mention} tiene **+{porcentaje}%** de probabilidad en giveaways.",
            ephemeral=True,
        )

    @app_commands.command(name="remove", description="Quita el bonus de un usuario")
    @app_commands.describe(usuario="Usuario")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove(self, interaction: discord.Interaction, usuario: discord.Member):
        bonuses = _get_bonuses(interaction.guild.id)
        if str(usuario.id) not in bonuses:
            return await interaction.response.send_message(
                f"{usuario.mention} no tiene bonus.", ephemeral=True
            )
        del bonuses[str(usuario.id)]
        _save_bonuses(interaction.guild.id, bonuses)
        await interaction.response.send_message(
            f"Bonus eliminado para {usuario.mention}.", ephemeral=True
        )

    @app_commands.command(name="list", description="Lista todos los bonus activos")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list(self, interaction: discord.Interaction):
        bonuses = _get_bonuses(interaction.guild.id)
        if not bonuses:
            return await interaction.response.send_message(
                "No hay bonus activos.", ephemeral=True
            )
        lines = []
        for uid, pct in bonuses.items():
            member = interaction.guild.get_member(int(uid))
            name = member.mention if member else f"`{uid}`"
            lines.append(f"{name} — **+{pct}%**")
        embed = discord.Embed(title="Bonus activos", description="\n".join(lines), color=0x2b2d31)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ── Cog ──────────────────────────────────────────────────────────────────────

class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._tasks: dict[str, asyncio.Task] = {}

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            giveaways = _get_giveaways(guild.id)
            for msg_id, data in giveaways.items():
                if not data.get("ended"):
                    end_time = datetime.fromisoformat(data["end_time"])
                    remaining = (end_time - datetime.now(timezone.utc)).total_seconds()
                    if remaining > 0:
                        task = asyncio.create_task(
                            self._wait_and_end(guild.id, int(msg_id), remaining)
                        )
                        self._tasks[msg_id] = task
                    else:
                        await self._end_giveaway(guild.id, int(msg_id))

    async def _wait_and_end(self, guild_id: int, message_id: int, delay: float):
        await asyncio.sleep(delay)
        await self._end_giveaway(guild_id, message_id)

    async def _end_giveaway(self, guild_id: int, message_id: int):
        giveaways = _get_giveaways(guild_id)
        data = giveaways.get(str(message_id))
        if not data or data.get("ended"):
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        channel = guild.get_channel(int(data["channel_id"]))
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            return

        participants = data.get("participants", [])
        bonuses = _get_bonuses(guild_id)
        winner_id = _pick_winner(participants, bonuses)

        end_time = datetime.fromisoformat(data["end_time"])
        embed = _build_embed(data["prize"], end_time, ended=True, winner_id=winner_id)
        await message.edit(embed=embed, view=None)

        if winner_id:
            await channel.send(f"🎉 ¡Felicidades <@{winner_id}>! Ganaste **{data['prize']}**.")
        else:
            await channel.send("Sin participantes para este giveaway.")

        data["ended"] = True
        data["winner_id"] = winner_id
        giveaways[str(message_id)] = data
        _save_giveaways(guild_id, giveaways)

    @app_commands.command(name="gcreate", description="Crea un giveaway")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gcreate(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GiveawayModal(self))

    @app_commands.command(name="gend", description="Termina un giveaway antes de tiempo")
    @app_commands.describe(message_id="ID del mensaje del giveaway")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gend(self, interaction: discord.Interaction, message_id: str):
        giveaways = _get_giveaways(interaction.guild.id)
        if message_id not in giveaways:
            return await interaction.response.send_message(
                "No encontré ese giveaway.", ephemeral=True
            )
        task = self._tasks.pop(message_id, None)
        if task:
            task.cancel()
        await self._end_giveaway(interaction.guild.id, int(message_id))
        await interaction.response.send_message("Giveaway terminado.", ephemeral=True)

    @app_commands.command(name="greroll", description="Rerollea el ganador de un giveaway")
    @app_commands.describe(message_id="ID del mensaje del giveaway")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def greroll(self, interaction: discord.Interaction, message_id: str):
        giveaways = _get_giveaways(interaction.guild.id)
        data = giveaways.get(message_id)
        if not data or not data.get("ended"):
            return await interaction.response.send_message(
                "Giveaway no encontrado o no ha terminado.", ephemeral=True
            )
        bonuses = _get_bonuses(interaction.guild.id)
        winner_id = _pick_winner(data.get("participants", []), bonuses)
        if winner_id:
            await interaction.response.send_message(
                f"🎉 Nuevo ganador: <@{winner_id}>! Felicidades por **{data['prize']}**."
            )
        else:
            await interaction.response.send_message(
                "Sin participantes para rerollear.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
    bot.tree.add_command(GbonusGroup())
