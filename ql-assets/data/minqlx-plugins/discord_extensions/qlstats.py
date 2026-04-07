from typing import Union

# noinspection PyPackageRequirements
from discord import Member, User, Embed, Color

# noinspection PyPackageRequirements
from discord import app_commands

from minqlx import Plugin


@app_commands.context_menu(name="qlstats")
@app_commands.guild_only()
async def qlstats(interaction, _item: Union[Member, User]):
    await _qlstats(interaction)


async def _qlstats(interaction):
    embed = Embed(color=Color.blurple())
    url = Plugin.get_cvar("qlx_discord_ext_qlstats_url")
    embed.url = url
    embed.title = "QL stats page"
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    bot.tree.add_command(qlstats)
