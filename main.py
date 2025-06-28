import discord
from discord.ext import tasks, commands
from discord import app_commands
import asyncio
from pymongo import MongoClient
from keep_alive import keep_alive
import os

TOKEN = os.environ['DISCORD_TOKEN']
MONGO_URI = os.environ['MONGO_URI']
GUILD_ID = int(os.environ['GUILD_ID'])  # Loaded from env
VANITY = ".gg/pussie"

intents = discord.Intents.default()
intents.members = True
intents.presences = True
client = commands.Bot(command_prefix="!", intents=intents)
tree = app_commands.CommandTree(client)

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["vanityBot"]
config_col = db["config"]

@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Bot is ready as {client.user}")
    scan_statuses.start()

def embed_msg(title, desc, color=discord.Color.blurple()):
    embed = discord.Embed(title=title, description=desc, color=color)
    return embed

@tree.command(name="setscanner", description="Set scan interval in seconds", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def setscanner(interaction: discord.Interaction, seconds: int):
    config_col.update_one({"_id": GUILD_ID}, {"$set": {"interval": seconds}}, upsert=True)
    scan_statuses.change_interval(seconds=seconds)
    await interaction.response.send_message(embed=embed_msg("✅ Scanner Updated", f"Interval set to **{seconds}** seconds."))

@tree.command(name="setrole", description="Set role to give on status match", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def setrole(interaction: discord.Interaction, role: discord.Role):
    config_col.update_one({"_id": GUILD_ID}, {"$set": {"role_id": role.id}}, upsert=True)
    await interaction.response.send_message(embed=embed_msg("✅ Role Set", f"Role set to **{role.name}**"))

@tree.command(name="setlog", description="Set channel to log matched users", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
    config_col.update_one({"_id": GUILD_ID}, {"$set": {"log_channel": channel.id}}, upsert=True)
    await interaction.response.send_message(embed=embed_msg("✅ Log Channel Set", f"Logs will be sent to {channel.mention}"))

@tree.command(name="setlogmessage", description="Set the message to display in the log embed", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def setlogmessage(interaction: discord.Interaction, message: str):
    config_col.update_one({"_id": GUILD_ID}, {"$set": {"log_message": message}}, upsert=True)
    await interaction.response.send_message(embed=embed_msg("✅ Log Message Updated", f"New log message: `{message}`"))

@tree.command(name="vanitymembers", description="List users with the vanity in their status", guild=discord.Object(id=GUILD_ID))
async def vanitymembers(interaction: discord.Interaction):
    guild = client.get_guild(GUILD_ID)
    matching = []

    for member in guild.members:
        if member.status in [discord.Status.online, discord.Status.idle, discord.Status.dnd]:
            for activity in member.activities:
                if isinstance(activity, discord.CustomActivity) and activity.name:
                    if VANITY in activity.name.lower():
                        matching.append(member.mention)
                        break

    if matching:
        await interaction.response.send_message(embed=embed_msg("👥 Vanity Members", "\n".join(matching)))
    else:
        await interaction.response.send_message(embed=embed_msg("👥 Vanity Members", "No members currently have the vanity in their status."))

@tree.command(name="ping", description="Check bot latency", guild=discord.Object(id=GUILD_ID))
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    await interaction.response.send_message(embed=embed_msg("🏓 Pong", f"Latency: `{latency}ms`"))

@tasks.loop(seconds=60)
async def scan_statuses():
    config = config_col.find_one({"_id": GUILD_ID})
    if not config:
        return

    interval = config.get("interval", 60)
    scan_statuses.change_interval(seconds=interval)

    guild = client.get_guild(GUILD_ID)
    role = guild.get_role(config.get("role_id"))
    channel = guild.get_channel(config.get("log_channel"))
    log_text = config.get("log_message", f"added `{VANITY}` in their status!")

    for member in guild.members:
        if member.status in [discord.Status.online, discord.Status.idle, discord.Status.dnd]:
            if member.bot:
                continue
            for activity in member.activities:
                if isinstance(activity, discord.CustomActivity) and activity.name:
                    if VANITY in activity.name.lower():
                        if role and role not in member.roles:
                            await member.add_roles(role)
                            embed = discord.Embed(
                                title="Vanity Detected",
                                description=f"{member.mention} {log_text}",
                                color=discord.Color.green()
                            )
                            embed.set_footer(text="Role has been assigned.")
                            if channel:
                                await channel.send(embed=embed)
    await asyncio.sleep(1)

# Error handling
@setscanner.error
@setrole.error
@setlog.error
@setlogmessage.error
async def error_handler(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message(embed=embed_msg("❌ Permission Denied", "You need **administrator** permission to use this command."), ephemeral=True)

keep_alive()
client.run(TOKEN)
