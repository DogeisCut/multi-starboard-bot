import discord
from discord.ext import commands
import json
import os
import logging
from datetime import datetime
from auth import token
import config

intents = discord.Intents.all()
intents.guilds = True

bot = commands.Bot(command_prefix=config.prefixes, intents=intents, case_insensitive=True)

data_file = 'starboards.json'

@bot.event
async def on_ready():
	activity = discord.Game(name=config.activty)
	await bot.change_presence(activity=activity)
	print(f'{bot.user} has connected.')

	if config.trigger_on_mention:
		@bot.event
		async def on_message(message):
			if bot.user.mentioned_in(message):
				await message.channel.send(f'My prefixes are: {", ".join(config.prefixes)}')

def load_data():
	if os.path.exists(data_file):
		with open(data_file, 'r') as f:
			return json.load(f)
	return {"starboards": []}

def save_data(data):
	with open(data_file, 'w') as f:
		json.dump(data, f, indent=4)

@bot.command(name='create')
async def create_starboard(ctx, *, args: str):
	if not ctx.message.author.guild_permissions.administrator:
		await ctx.reply('You need to be an admin to create starboards!')
		return
	
	args = args.split()
	channel_arg = next((arg.split('=')[1] for arg in args if arg.startswith('--channel=')), "this")
	name = next((arg.split('=')[1] for arg in args if arg.startswith('--name=')), "Starboard")
	emojis_arg = next((arg.split('=')[1] for arg in args if arg.startswith('--emojis=')), "🌟,⭐,✨")
	requirement_arg = next((arg.split('=')[1] for arg in args if arg.startswith('--requirement=') or arg.startswith('--count=')), 5)
	self_starring_arg = next((arg.split('=')[1] for arg in args if arg.startswith('--allow_self_star=') or arg.startswith('--self=')), "false")
	color_arg = next((arg.split('=')[1] for arg in args if arg.startswith('--color=') or arg.startswith('--col=') or arg.startswith('--colour=')), "#ffffff")

	channel_id = ctx.channel.id if channel_arg.lower() == "this" else int(channel_arg)
	
	try:
		requirement = int(requirement_arg)
	except ValueError:
		await ctx.reply('Invalid value for `Star Count`. It must be an integer.')
		return
	
	self_starring = self_starring_arg.lower() == 'true'
	
	new_starboard = {
		"emojis": [emoji for emoji in emojis_arg.split(',')],
		"name": name,
		"channel_id": str(channel_id),
		"guild_id": str(ctx.guild.id),
		"emoji_count": requirement,
		"allow_self_starring": self_starring,
		"color": color_arg,
		"starred_messages": []
	}

	data = load_data()
	data['starboards'].append(new_starboard)
	save_data(data)
	await ctx.send(f'Starboard **{name}** created!')

@bot.command(name='remove')
async def remove_starboard(ctx, identifier: str):
	if not ctx.message.author.guild_permissions.administrator:
		await ctx.reply('You need to be an admin to remove starboards!')
		return

	data = load_data()
	starboards = data['starboards']
	starboard = next((s for s in starboards if s['name'] == identifier or s['channel_id'] == identifier), None)
	
	if starboard:
		starboards.remove(starboard)
		save_data(data)
		await ctx.send(f'Starboard **{starboard["name"]}** removed!')
	else:
		await ctx.send('Starboard not found.')

@bot.command(name='edit')
async def edit_starboard(ctx, identifier: str, property: str, value):
	if not ctx.message.author.guild_permissions.administrator:
		await ctx.reply('You need to be an admin to edit starboards!')
		return
	
	data = load_data()
	starboard = next((s for s in data['starboards'] if s['name'] == identifier or s['channel_id'] == identifier), None)
	
	if starboard:
		if property in starboard:
			if property in ['emoji_count', 'allow_self_starring']:
				starboard[property] = int(value) if property == 'emoji_count' else value.lower() == 'true'
			elif property == 'emojis':
				starboard[property] = [emoji for emoji in value.split(',')]
			else:
				starboard[property] = value
			save_data(data)
			await ctx.send(f'Starboard **{starboard["name"]}** updated: **{property}** set to **{value}**.')
		else:
			await ctx.send('Invalid property to edit.')
	else:
		await ctx.send('Starboard not found.')

@bot.event
async def on_raw_reaction_add(payload):
	emoji = payload.emoji
	user_id = payload.user_id
	channel_id = payload.channel_id
	message_id = payload.message_id
	guild_id = payload.guild_id

	if user_id == bot.user.id:
		return
		
	message_channel = bot.get_channel(channel_id)
	if message_channel is None:
		return
	
	message = await message_channel.fetch_message(message_id)

	data = load_data()
	starboards = [s for s in data['starboards'] if s['guild_id'] == str(guild_id)]
	
	for starboard in starboards:
		if str(emoji) in starboard['emojis']:
			emoji_count = sum(
				r.count for r in message.reactions 
				if str(r.emoji) in starboard['emojis'] and 
				(r.me is False) and 
				(user_id != message.author.id or starboard['allow_self_starring'])
			)

			if emoji_count >= starboard['emoji_count']:
				starred_message = next((msg for msg in starboard['starred_messages'] if msg['message'] == str(message.id)), None)

				embed = discord.Embed(
					description=message.content,
					timestamp=datetime.utcnow()
				)
				embed.set_author(
					name=message.author.display_name,
					icon_url=message.author.avatar.url
				)

				embed.add_field(name="**Source**", value=f"[Jump!]({message.jump_url})", inline=False)
				
				if message.attachments:
					for attachment in message.attachments:
						if not attachment.url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.mp4', '.webm', '.webp')):
							embed.add_field(name="**Attachment**", value=attachment.url, inline=False)

				if message.attachments:
					embed.set_image(url=message.attachments[0].url)

				footer_text = str(message.id)
				embed.set_footer(text=footer_text)

				embed.color = int(starboard['color'].lstrip('#'), 16)

				if starred_message:
					starboard_message_id = starred_message['starboard_message']
					starboard_channel = bot.get_channel(int(starboard['channel_id']))
					if starboard_channel:
						existing_message = await starboard_channel.fetch_message(starboard_message_id)
						await existing_message.edit(content=f"{starboard['emojis'][0]} **{emoji_count}** <#{starboard_channel.id}>", embeds=[embed])
						starred_message['stars'] = emoji_count
						save_data(data)
				else:
					channel = bot.get_channel(int(starboard['channel_id']))
					if channel is None:
						return
					starboard_channel = bot.get_channel(int(starboard['channel_id']))
					sent_message = await channel.send(content=f"{starboard['emojis'][0]} **{emoji_count}** <#{starboard_channel.id}>", embeds=[embed])
					starred_message = {
						"message": str(message.id),
						"starboard_message": sent_message.id,
						"stars": emoji_count
					}
					starboard['starred_messages'].append(starred_message)
					save_data(data)
				break

bot.run(token)
