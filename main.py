"""
DISCORD LEADERBOARD BOT
=======================
This bot connects to your SiteGround MySQL database and displays 
game leaderboards in Discord using a dropdown menu system.

Created for: ofthebones.xyz leaderboards
"""

import discord
from discord.ext import commands
import mysql.connector
import os
from typing import List, Dict, Any
import asyncio
from threading import Thread
from flask import Flask
import time

# ============================================================================
# BOT CONFIGURATION
# ============================================================================

last_leaderboard_time = 0
COOLDOWN_SECONDS = 300

# Simple web server for Render health checks
app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

# Bot settings - these control how the bot behaves
BOT_PREFIX = "!"  # Commands start with ! (like !graveyard)
BOT_DESCRIPTION = "Game Leaderboard Bot - Shows top players from database"

# Database configuration - this tells the bot how to connect to your MySQL
DATABASE_CONFIG = {
    'host': 'gtxm1069.siteground.biz',      # Your SiteGround database server
    'database': 'dbdty6inyb4gbs',           # Your database name
    'user': 'ucghqjnsgrb03',                # Your database username
    'password': os.getenv('DB_PASSWORD'),    # Password from environment variable (secure!)
    'charset': 'utf8mb4',                   # Character encoding for emojis/special chars
    'autocommit': True                      # Automatically save database queries
}

# ============================================================================
# LEADERBOARD DEFINITIONS
# ============================================================================

LEADERBOARDS = {
    "general": {
        "name": "General Leaderboard",
        "table": "Leaderboard", 
        "join_users": True,
    },
    "3ull": {
        "name": "Playa3ull",
        "table": "3ull_tournament_leaderboard",
        "join_users": False,
    },
    "dragon": {
        "name": "Ancient Dragon Alliance", 
        "table": "leaderboard_dragon",
        "join_users": False,
    },
    "gingerbread": {
        "name": "Gingerbread Squad",
        "table": "leaderboard_gingerbread", 
        "join_users": False,
    },
    "promo": {
        "name": "Promo Facie",
        "table": "leaderboard_promo",
        "join_users": False, 
    },
    "squeak": {
        "name": "World of Squeak",
        "table": "leaderboard_squeak",
        "join_users": False,
    },
    "algo apes": {
        "name": "Algo Apes",
        "table": "algoapes_tournament_leaderboard",
        "join_users": False,
    }
}

# ============================================================================
# BOT SETUP
# ============================================================================

# Set up bot permissions (intents)
intents = discord.Intents.default()
intents.message_content = True  # Allow bot to read message content

# Create the bot
bot = commands.Bot(
    command_prefix=BOT_PREFIX,
    description=BOT_DESCRIPTION, 
    intents=intents
)

# ============================================================================
# DATABASE CONNECTION FUNCTIONS
# ============================================================================

async def get_database_connection():
    """
    Creates a connection to the MySQL database.
    This function handles errors gracefully so the bot doesn't crash.
    
    Returns:
        mysql.connector connection object or None if failed
    """
    try:
        connection = mysql.connector.connect(**DATABASE_CONFIG)
        return connection
    except mysql.connector.Error as error:
        print(f"❌ Database connection failed: {error}")
        return None

async def fetch_leaderboard_data(leaderboard_key: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetches leaderboard data from the database.
    """
    
    # Get leaderboard configuration
    config = LEADERBOARDS.get(leaderboard_key)
    if not config:
        print(f"❌ No config found for key: {leaderboard_key}")
        return []
    
    # Connect to database
    connection = await get_database_connection()
    if not connection:
        print(f"❌ Database connection failed for {leaderboard_key}")
        return []
    
    try:
        cursor = connection.cursor(dictionary=True)
        
        if config["join_users"]:
            # For general leaderboard - need to join with Users table to get nicknames
            query = """
                SELECT u.nickname, l.kills, l.levels_reached
                FROM {} l
                JOIN Users u ON l.user_id = u.user_id  
                ORDER BY l.levels_reached DESC, l.kills DESC
                LIMIT %s
            """.format(config["table"])
        else:
            # For tournament leaderboards - check table structure
            if leaderboard_key == "3ull":
                # 3ull table has user_id column with usernames
                query = """
                    SELECT user_id as nickname, kills, levels_reached
                    FROM {}
                    ORDER BY levels_reached DESC, kills DESC  
                    LIMIT %s
                """.format(config["table"])
            else:
                # Other tournament tables have username column
                query = """
                    SELECT username as nickname, kills, levels_reached
                    FROM {}
                    ORDER BY levels_reached DESC, kills DESC  
                    LIMIT %s
                """.format(config["table"])
        
        print(f"🔍 Executing query for {leaderboard_key}: {query}")
        cursor.execute(query, (limit,))
        results = cursor.fetchall()
        print(f"📊 Found {len(results)} results for {leaderboard_key}")
        
        return results
        
    except mysql.connector.Error as error:
        print(f"❌ Database query failed for {leaderboard_key}: {error}")
        return []
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

# ============================================================================
# DISCORD EMBED CREATION
# ============================================================================

def create_leaderboard_embed(leaderboard_key: str, data: List[Dict[str, Any]]) -> discord.Embed:
    """
    Creates a clean Discord embed showing leaderboard data.
    """
    
    config = LEADERBOARDS[leaderboard_key]
    
    # Create the embed with black color and clean title
    embed = discord.Embed(
        title=f"{config['name']}",
        color=0x000000  # Black color
    )
    
    # Clean footer
    embed.set_footer(text="Graveyard Antics TD")
    
    if not data:
        embed.description = "No players found in this leaderboard."
        return embed
    
    # Create clean numbered leaderboard
    leaderboard_text = ""
    
    for i, player in enumerate(data, 1):
        # Simple numbering - no medal emojis
        kills_formatted = f"{player['kills']:,}"
        
        # Clean format: number, name, stats
        leaderboard_text += f"{i}. **{player['nickname']}** - {player['levels_reached']} waves survived, {kills_formatted} enemies destroyed\n"
    
    # Use description instead of add_field to avoid subtitle
    embed.description = leaderboard_text
    
    return embed

# ============================================================================
# DROPDOWN MENU CLASS
# ============================================================================

class LeaderboardDropdown(discord.ui.Select):
    """
    This creates the dropdown menu that users can interact with.
    When they select an option, it shows that leaderboard.
    """
    
    def __init__(self):
        # Create options for each leaderboard
        options = []
        for key, config in LEADERBOARDS.items():
            options.append(
                discord.SelectOption(
                    label=config["name"],  # Clean label without emoji processing
                    value=key
                )
            )
        
        super().__init__(
            placeholder="Choose a leaderboard to view...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """
        This function runs when someone selects an option from the dropdown.
        It fetches the data and shows the leaderboard.
        """
        print(f"🔄 Dropdown callback triggered for: {self.values[0]}")
        print(f"🔄 Interaction ID: {interaction.id}")
        print(f"🔄 User: {interaction.user}")
    
        try:
            # Show "thinking" message while we fetch data
            print("🔄 About to defer interaction...")
            await interaction.response.defer()
            print("✅ Interaction deferred successfully")
        
            # Get the selected leaderboard
            selected_leaderboard = self.values[0]
            print(f"🔄 Processing leaderboard: {selected_leaderboard}")
        
            # Fetch data from database
            data = await fetch_leaderboard_data(selected_leaderboard)
            print(f"🔄 Got {len(data)} records from database")
        
            # Create embed with the data
            embed = create_leaderboard_embed(selected_leaderboard, data)
            print("🔄 Created embed")
        
            # Send the leaderboard
            print("🔄 About to send followup...")
            await interaction.followup.send(embed=embed, ephemeral=False)
            print(f"✅ Sent leaderboard for: {selected_leaderboard}")
        
        except Exception as e:
            print(f"❌ Error in callback: {e}")
            print(f"❌ Error type: {type(e)}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Something went wrong!", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Something went wrong!", ephemeral=True)
            except:
                print("❌ Could not send error message")

class LeaderboardView(discord.ui.View):
    """
    This class holds the dropdown menu and handles timeouts.
    """
    
    def __init__(self):
        print("🔧 Creating LeaderboardView...")
        super().__init__(timeout=300)  # Menu expires in 5 minutes
        print("🔧 Adding dropdown to view...")
        self.add_item(LeaderboardDropdown())
        print("✅ LeaderboardView created successfully")
    
    async def on_timeout(self):
        """Called when the menu expires"""
        # Disable all components when timeout occurs
        for item in self.children:
            item.disabled = True

# ============================================================================
# BOT COMMANDS
# ============================================================================

@bot.command(name='graveyard', aliases=['gy'])
async def leaderboards_command(ctx):
    """
    Main command that users type: !graveyard
    This shows the dropdown menu to select which leaderboard to view.
    
    Args:
        ctx: Discord context (contains info about who sent the command, where, etc.)
    """
    global last_leaderboard_time
    
    current_time = time.time()
    
    # Check if cooldown is still active
    if current_time - last_leaderboard_time < COOLDOWN_SECONDS:
        remaining_time = COOLDOWN_SECONDS - (current_time - last_leaderboard_time)
        minutes = int(remaining_time // 60)
        seconds = int(remaining_time % 60)
        
        await ctx.send(f"Leaderboard is cooling down. Try again in {minutes}m {seconds}s.")
        return
    
    # Update the last command time
    last_leaderboard_time = current_time
    
    print(f"🎯 !graveyard command triggered by {ctx.author}")
    
    # Create embed for the main menu
    embed = discord.Embed(
        title="🏆 Graveyard Antics TD Leaderboards 🏆",
        description="Select a leaderboard from the dropdown menu below to view the top 10 players & scores for that leaderboard",
        color=0x000000  # Black color to match
    )
    
    embed.add_field(
        name="Available Leaderboards", 
        value="\n".join([config['name'] for config in LEADERBOARDS.values()]),  # No emojis
        inline=False
    )
    
    embed.set_footer(text="Graveyard Antics TD | Menu expires in 5 minutes")
    
    # Create the dropdown view
    print("🎯 Creating dropdown view...")
    view = LeaderboardView()
    
    # Send the message with dropdown
    print("🎯 Sending message with dropdown...")
    await ctx.send(embed=embed, view=view)
    print("✅ Message sent successfully")

# ============================================================================
# BOT EVENTS
# ============================================================================

@bot.event
async def on_ready():
    """
    This runs when the bot successfully connects to Discord.
    It's like the bot saying "I'm online and ready!"
    """
    print(f'✅ Bot is ready!')
    print(f'📊 Logged in as: {bot.user.name}')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'🎯 Loaded {len(LEADERBOARDS)} leaderboards')
    print('🚀 Bot is now online and ready to serve leaderboards!')
    
    # Test database connection on startup
    connection = await get_database_connection()
    if connection:
        print('✅ Database connection successful!')
        connection.close()
    else:
        print('❌ Database connection failed!')

# Temporarily disabled error handler to debug double embeds
# @bot.event
# async def on_command_error(ctx, error):
#     """
#     This handles errors gracefully so users get helpful messages
#     instead of the bot just breaking.
#     """
#     if isinstance(error, commands.CommandNotFound):
#         # Don't respond to invalid commands to avoid spam
#         return
#     else:
#         # Log other errors with more detail
#         print(f"❌ Command error in {ctx.command}: {error}")
#         print(f"❌ Error type: {type(error)}")
#         print(f"❌ Full error: {str(error)}")
#         await ctx.send("❌ Something went wrong! Please try again later.")

# ============================================================================
# RUN THE BOT
# ============================================================================

Thread(target=run_web, daemon=True).start()
if __name__ == "__main__":
    """
    This is where the bot actually starts running.
    It gets the bot token from environment variables for security.
    """
    
    # Get bot token from environment variable
    bot_token = os.getenv('DISCORD_BOT_TOKEN')
    
    if not bot_token:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable not set!")
        print("Please set your Discord bot token in the environment variables.")
        exit(1)
    
    if not os.getenv('DB_PASSWORD'):
        print("❌ Error: DB_PASSWORD environment variable not set!")
        print("Please set your database password in the environment variables.")
        exit(1)
    
    # Start the bot
    print("🚀 Starting Discord Leaderboard Bot...")
    bot.run(bot_token)
