import discord
from discord.ext import commands
import json
import os
import praw
import random
from collections import defaultdict
import asyncio
import time
import sqlite3
from datetime import datetime
from discord.ui import Select, View


# Configuration de l'API Reddit
reddit = praw.Reddit(
    client_id='TOKEN',
    client_secret='TOKEN',
    user_agent='discord:bot_meme:v1.0 (by u/TAYOKENytd)',
)

TOKEN = 'TOKEN'
AUTHORIZED_USER_ID = 301312439989960704

intents = discord.Intents.all() 
intents.messages = True
intents.reactions = True
client = commands.Bot(command_prefix='?', intents=intents)

# Cache pour les configurations et leaderboards
config_cache = {}
leaderboard_cache = {}
last_save_time = {}
SAVE_INTERVAL = 60
db_path = os.path.join(os.path.dirname(__file__), 'media_links.db')

# Initialisation de la base de données
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS media_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        message_id INTEGER,
        author_id INTEGER,
        media_url TEXT
    )
""")
conn.commit()
# Cache pour les memes Reddit
meme_cache = []
last_meme_refresh = 0
MEME_CACHE_REFRESH = 3600  # Rafraîchir le cache toutes les heures
LOG_FILE = 'bot.log' # Fichier de logs (sera enregistrer dans le dossier principal du serveur)
# TODO: Mettre les logs dans le fichier data/id_guild/bot.log
NOW = datetime.now() # Date et heure actuelle pour les logs

# Fonction pour récupérer le dossier data spécifique à chaque serveur
def get_server_data_directory(guild_id):
    directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', str(guild_id))
    if not os.path.exists(directory):
        os.makedirs(directory)
    return directory

# Fonction pour récupérer le fichier de configuration spécifique à chaque serveur
def get_config_file(guild_id):
    return os.path.join(get_server_data_directory(guild_id), 'config.json')

# Fonction pour récupérer le fichier leaderboard spécifique à chaque serveur
def get_leaderboard_file(guild_id):
    return os.path.join(get_server_data_directory(guild_id), 'leaderboard.json')

def get_log_file(guild_id):
    return os.path.join(get_server_data_directory(guild_id), 'log.txt')

# Paramètres de scoring
positive_reaction_threshold = 1
negative_reaction_threshold = 3
positive_points = 2
negative_points = 1
recycled_reaction_threshold = 5
recycled_points = 20

# Fonction pour charger les données du leaderboard avec cache
def load_leaderboard(guild_id):
    guild_id_str = str(guild_id)
    if guild_id_str in leaderboard_cache:
        return leaderboard_cache[guild_id_str]
        
    leaderboard_file = get_leaderboard_file(guild_id)
    if not os.path.isfile(leaderboard_file):
        leaderboard_cache[guild_id_str] = defaultdict(int)
    else:
        with open(leaderboard_file, 'r') as f:
            leaderboard_cache[guild_id_str] = defaultdict(int, json.load(f))
    
    return leaderboard_cache[guild_id_str]

# Fonction pour sauvegarder les données du leaderboard
def save_leaderboard(guild_id, force=False):
    guild_id_str = str(guild_id)
    current_time = time.time()
    
    # Sauvegarde uniquement si forcée ou si l'intervalle de temps est écoulé
    if force or guild_id_str not in last_save_time or (current_time - last_save_time.get(guild_id_str, 0)) > SAVE_INTERVAL:
        if guild_id_str in leaderboard_cache:
            leaderboard_file = get_leaderboard_file(guild_id)
            with open(leaderboard_file, 'w') as f:
                json.dump(dict(leaderboard_cache[guild_id_str]), f, indent=4)
            last_save_time[guild_id_str] = current_time

# Fonction pour charger la configuration du serveur avec cache
def load_config(guild_id):
    guild_id_str = str(guild_id)
    if guild_id_str in config_cache:
        return config_cache[guild_id_str]
    
    # Configuration par défaut
    default_config = {
        "reaction_channel_id": None,
        "positive_reaction_threshold": 1,
        "negative_reaction_threshold": 3,
        "recycled_reaction_threshold": 5,
        "positive_points": 2,
        "negative_points": 1,
        "recycled_points": 20
    }
    
    config_file = get_config_file(guild_id)
    
    if not os.path.isfile(config_file):
        config_cache[guild_id_str] = default_config.copy()
    else:
        with open(config_file, 'r') as f:
            loaded_config = json.load(f)
        # Fusion avec la configuration par défaut
        merged_config = default_config.copy()
        merged_config.update(loaded_config)
        config_cache[guild_id_str] = merged_config
    
    return config_cache[guild_id_str]

# Fonction pour sauvegarder la configuration du serveur
def save_config(guild_id):
    guild_id_str = str(guild_id)
    if guild_id_str in config_cache:
        config_file = get_config_file(guild_id)
        with open(config_file, 'w') as f:
            json.dump(config_cache[guild_id_str], f, indent=4)

# Fonction pour rafraîchir le cache de memes
async def refresh_meme_cache():
    global meme_cache, last_meme_refresh
    current_time = time.time()
    
    if not meme_cache or (current_time - last_meme_refresh) > MEME_CACHE_REFRESH:
        subreddit = reddit.subreddit('shitposting')
        posts = list(subreddit.hot(limit=100))
        meme_cache = [post for post in posts if post.url.endswith(('jpg', 'jpeg', 'png', 'gif', 'gifv')) or 'v.redd.it' in post.url]
        last_meme_refresh = current_time
    
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{NOW}]: Meme cache refreshed\n Links: \n")
        for post in meme_cache:
            f.write(f"{post.url}\n")

# Tâche en arrière-plan pour sauvegarder les données périodiquement
async def background_save():
    while True:
        await asyncio.sleep(SAVE_INTERVAL)
        for guild_id in leaderboard_cache:
            save_leaderboard(int(guild_id))
        for guild_id in config_cache:
            save_config(int(guild_id))

@client.event
async def on_ready():
    print(f"[{NOW}] Démarré \n ______________________________________________________________________________________________________")
    client.loop.create_task(background_save())

@client.command()
async def channel_config(ctx, channel: discord.TextChannel = None):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("Vous devez être administrateur pour configurer le salon.")
        return
    
    config_data = load_config(ctx.guild.id)
    
    if channel is None:
        current_channel = config_data["reaction_channel_id"]
        if current_channel:
            channel_obj = await ctx.guild.fetch_channel(current_channel)
            await ctx.send(f"Le salon pour les réactions est actuellement : {channel_obj.mention}.")
        else:
            await ctx.send("Aucun salon pour les réactions n'a été configuré.")
        return
    
    config_data["reaction_channel_id"] = channel.id
    save_config(ctx.guild.id)
    
    await ctx.send(f"Le salon pour les réactions a été configuré : {channel.mention}.")
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{NOW}]: Le salon de reaction de {ctx.guild} a été configuré : {channel.mention} par {ctx.author.id}\n")

@client.command()
async def threshold_config(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("Vous devez être administrateur pour configurer les seuils.")
        return

    # Charger la configuration actuelle
    config_data = load_config(ctx.guild.id)

    # Créer un menu déroulant pour sélectionner le seuil à modifier
    select = Select(
        placeholder="Choisissez le seuil à configurer",
        options=[
            discord.SelectOption(label="Réactions positives (👍)", value="positive_reaction_threshold", description=f"Actuel : {config_data['positive_reaction_threshold']}"),
            discord.SelectOption(label="Réactions négatives (👎)", value="negative_reaction_threshold", description=f"Actuel : {config_data['negative_reaction_threshold']}"),
            discord.SelectOption(label="Réactions recyclées (♻️)", value="recycled_reaction_threshold", description=f"Actuel : {config_data['recycled_reaction_threshold']}"),
        ]
    )

@client.command()
async def points_config(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("Vous devez être administrateur pour configurer les points")
        return

    # Charger la configuration actuelle
    config_data = load_config(ctx.guild.id)

    
    select = Select(
        placeholder="Choisissez le seuil à configurer",
        options=[
            discord.SelectOption(label="Réactions positives (👍)", value="positive_points", description=f"Actuel : {config_data['positive_points']}"),
            discord.SelectOption(label="Réactions négatives (👎)", value="negative_points", description=f"Actuel : {config_data['negative_points']}"),
            discord.SelectOption(label="Réactions recyclées (♻️)", value="recycled_points", description=f"Actuel : {config_data['recycled_points']}"),
        ]
    )

    # Fonction appelée lorsque l'utilisateur fait une sélection
    async def select_callback(interaction):
        await interaction.response.send_message(f"Vous avez choisi : {select.values[0]}. Veuillez entrer la nouvelle valeur :", ephemeral=True)

        try:
            # Attendre la réponse de l'utilisateur
            response = await client.wait_for(
                'message',
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=30
            )
            new_value = int(response.content)

            # Mettre à jour la configuration
            config_data[select.values[0]] = new_value
            save_config(ctx.guild.id)

            await ctx.send(f"Le seuil `{select.values[0]}` a été mis à jour à {new_value}.")
        except asyncio.TimeoutError:
            await ctx.send("Temps écoulé. Veuillez réessayer.")

    # Associer le callback au menu
    select.callback = select_callback

    # Ajouter le menu à une vue
    view = View()
    view.add_item(select)

    # Envoyer le menu à l'utilisateur
    await ctx.send("Choisissez le seuil que vous souhaitez configurer :", view=view)
    


@client.command()
async def leaderboard(ctx):
    leaderboard_data = load_leaderboard(ctx.guild.id)
    sorted_leaderboard = sorted(leaderboard_data.items(), key=lambda x: x[1], reverse=True)
    
    if not sorted_leaderboard:
        await ctx.send("Le leaderboard est vide.")
        return
    
    embed = discord.Embed(
        title="🏆 Leaderboard 🏆",
        description="Voici les meilleurs chomeurs du serveur !",
        color=discord.Color.blue()
    )

    for i, (user_id, score) in enumerate(sorted_leaderboard[:10], start=1):
        try:
            user = await client.fetch_user(int(user_id))
            name = user.name
        except:
            name = f"Utilisateur {user_id}"
        
        rank_emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."

        embed.add_field(
            name=f"{rank_emoji} {name}",
            value=f"{score} points",
            inline=False
        )

    embed.set_footer(text="Leaderboard")
    await ctx.send(embed=embed)

@client.command()
async def meme(ctx):
    await refresh_meme_cache()
    
    if not meme_cache:
        await ctx.send("Je n'ai pas pu trouver de memes pour le moment, essaie à nouveau plus tard !")
        return
    
    choice = random.randint(1,2)
    if choice == 1:
        post = random.choice(meme_cache)
        await ctx.send(post.url)

    else:
        cursor.execute('SELECT media_url FROM media_links WHERE guild_id = ?', (ctx.guild.id,))
        media_urls = cursor.fetchall()
        post = random.choice(media_urls)
        await ctx.send(post)

@client.command()
@commands.is_owner()
async def add_points(ctx, member: discord.Member, points: int):
    leaderboard_data = load_leaderboard(ctx.guild.id)
    user_id = str(member.id)
    
    leaderboard_data[user_id] += points
    save_leaderboard(ctx.guild.id, force=True)
    
    await ctx.send(f"{points} points ajoutés à {member.name}. Nouveau score: {leaderboard_data[user_id]} points.")

@client.event
async def on_message(message):
    # Ignore les messages des bots
    if message.author.bot:
        return

    guild_id = message.guild.id
    
    # Vérifier si le message contient "sigma"
    if "sigma" in message.content.lower().split() or "kms" in message.content.lower().split():
        # URL de la vidéo à envoyer
        video_url = "https://cdn.discordapp.com/attachments/856614592570720267/1362106216536346724/CGiAn47Q8ZYNdIZC.mp4?ex=68012fc4&is=67ffde44&hm=8335a7b9d4c5fce05f6b511d378b2cf15fe35368863614dac5bfb38a2c97e7b1&"
        await message.channel.send(video_url)
    
    # Ajout de points basé sur le nombre de mots
    words_count = len(message.content.split())
    if words_count > 0:
        leaderboard_data = load_leaderboard(guild_id)
        leaderboard_data[str(message.author.id)] += words_count
    
    # Gestion des réactions pour les messages avec pièces jointes
    config_data = load_config(guild_id)
    reaction_channel_id = config_data.get("reaction_channel_id")
    
    if message.channel.id == reaction_channel_id and message.attachments:  
        await message.add_reaction('👍')
        await message.add_reaction('👎')
        await message.add_reaction('♻️')

    # Traitement des commandes
    await client.process_commands(message)

@client.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    message = reaction.message
    guild_id = message.guild.id
    config_data = load_config(guild_id)
    reaction_channel_id = config_data.get("reaction_channel_id")
    
    if message.channel.id != reaction_channel_id:
        return

    author_id = str(message.author.id)
    leaderboard_data = load_leaderboard(guild_id)
    should_save = False

    positive_reaction_threshold = config_data["positive_reaction_threshold"]
    negative_reaction_threshold = config_data["negative_reaction_threshold"]
    recycled_reaction_threshold = config_data["recycled_reaction_threshold"]
    positive_points = config_data["positive_points"]
    negative_points = config_data["negative_points"]
    recycled_points = config_data["recycled_points"]

    if reaction.emoji == '👍' and reaction.count >= positive_reaction_threshold:
        leaderboard_data[author_id] += positive_points
        should_save = True
        if message.attachments:
            for attachment in message.attachments:
                cursor.execute("""
                    INSERT INTO media_links 
                    (guild_id, message_id, author_id, media_url)
                    VALUES (?, ?, ?, ?)
                """, (guild_id, message.id, author_id, attachment.url))
                conn.commit()
                with open(LOG_FILE, 'a') as f:
                    f.write(f"[{NOW}]: {attachment.url} ajouté dans la Base de Données de {guild_id} venant de {author_id}\n")
    
    elif reaction.emoji == '👎' and reaction.count >= negative_reaction_threshold:
        leaderboard_data[author_id] -= negative_points
        should_save = True
    
    elif reaction.emoji == '♻️' and reaction.count >= recycled_reaction_threshold:
        leaderboard_data[author_id] -= recycled_points
        should_save = True
        
        await message.delete()
        await message.channel.send(f"{message.author.mention} a atteint {recycled_reaction_threshold} ♻️ réactions et le message a été supprimé, {recycled_points} point(s) retiré(s).")
    
    if should_save:
        save_leaderboard(guild_id)

@client.command()
async def points(ctx):
    leaderboard_data = load_leaderboard(ctx.guild.id)
    user_id = str(ctx.author.id)
    points = leaderboard_data[user_id]  # defaultdict retournera 0 si non existant
    
    await ctx.send(f"{ctx.author.mention}, vous avez {points} point(s).")

@client.command()
async def show_media(ctx):
    guild_id = ctx.guild.id
    cursor.execute('SELECT media_url FROM media_links WHERE guild_id = ?', (guild_id,))
    media_urls = cursor.fetchall()
    
    if not media_urls:
        await ctx.send("Aucun media n'a été trouvé.")
        return
        
    embed = discord.Embed(
        title="📸 Médias 📸",
        description="Voici les médias postés dans le salon de réactions.",
        color=discord.Color.green()
    )

    for i, (media_url,) in enumerate(media_urls, start=1):
        embed.add_field(
            name=f"Media {i}",
            value=media_url,
            inline=False
        )
    
    await ctx.send(embed=embed)

@client.command()
@commands.is_owner()
async def stop(ctx):
    # Sauvegarde forcée
    for guild_id in leaderboard_cache:
        save_leaderboard(int(guild_id), force=True)
    for guild_id in config_cache:
        save_config(int(guild_id))
    
    # Fermeture propre de la base de données
    conn.close()
    
    print('Arrêt du bot...')
    await ctx.send("Sauvegarde des données et arrêt du bot...")
    await client.close()

client.run(TOKEN)
