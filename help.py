"""
help.py — Comando /help con todos los comandos del bot.
"""

import discord
from discord import app_commands
from discord.ext import commands


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Lista de comandos del bot")
    async def help_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Comandos del bot", color=0x2b2d31)

        embed.add_field(name="🎉 Giveaways", value=(
            "`/gcreate` — Crea un giveaway (abre ventana con Premio, Duración, Canal)\n"
            "`/gend <id>` — Termina un giveaway antes de tiempo\n"
            "`/greroll <id>` — Rerollea el ganador\n"
            "`/gbonus add @user %` — Da bonus de probabilidad (3-50%)\n"
            "`/gbonus remove @user` — Quita el bonus\n"
            "`/gbonus list` — Lista bonus activos\n\n"
            "**Ejemplos:**\n"
            "`/gcreate` → abre ventana → Premio: Nitro | Duración: 2h | Canal: giveaways\n"
            "`/gbonus add @chisqeado 20` → +20% de ganar\n"
            "`/gend 1234567890` → termina el giveaway con ese ID"
        ), inline=False)

        embed.add_field(name="📨 Invitaciones", value=(
            "`/setinvite channel #canal` — Canal de notificaciones de milestone\n"
            "`/setinvite threshold <n> [recompensa]` — Cada cuántas invitaciones notifica\n"
            "`/setinvite altdays <1-7>` — Días mínimos de cuenta para no ser alt\n"
            "`/invites [@user]` — Ver invitaciones de alguien\n"
            "`/invitetop` — Top 5 inviters\n"
            "`/resetinvites` — Reinicia todas las estadísticas\n\n"
            "**Ejemplos:**\n"
            "`/setinvite threshold 10 tiene 10% más de ganar en giveaways`\n"
            "`/setinvite altdays 3` → ignora cuentas menores a 3 días\n"
            "`/invites @chisqeado` → muestra sus invitaciones"
        ), inline=False)

        embed.set_footer(text="Solo admins pueden usar comandos de configuración.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
