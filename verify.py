import logging
import os
from typing import Dict

import interactions
from pyairtable import Table
from pyairtable.formulas import match

# Airtable parameters
airtable_token = os.environ['AIRTABLE_TOKEN']
base_id = os.environ['AIRTABLE_BASE_ID']
members_table = Table(airtable_token, base_id, os.environ['AIRTABLE_MEMBERS_TABLE_ID'])
discord_table = Table(airtable_token, base_id, os.environ['AIRTABLE_DISCORD_TABLE_ID'])

# Discord parameters
discord_token = os.environ['DISCORD_TOKEN']
guild_id = int(os.environ['DISCORD_GUILD_ID'])
channel_id = int(os.environ['DISCORD_CHANNEL_ID'])
verified_role_id = int(os.environ['DISCORD_VERIFIED_ROLE_ID'])
manager_role_id = int(os.environ['DISCORD_MANAGER_ROLE_ID'])
ic_role_id = int(os.environ['DISCORD_IC_ROLE_ID'])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def upsert_discord(m: interactions.Member) -> str:
    d = discord_table.first(formula=match({'ID': m.id}))
    if d is None:
        d = discord_table.create({
            'Name': f'{m.user.username}#{m.user.discriminator}',
            'ID': int(m.id),
        })
    return d['id']


def link_member(m: interactions.Member, unite_id: int):
    discord_rec_id = upsert_discord(m)
    member = members_table.first(formula=match({'Member Number': unite_id}))
    if member is None:
        return False
    d = set(member['fields'].get('Discord', []))
    d.add(discord_rec_id)
    members_table.update(member['id'], {'Discord': list(d)})
    return True


bot = interactions.Client(token=discord_token, intents=interactions.Intents.ALL)


@bot.event
async def on_start():
    logger.info('Bot started.')


@bot.event
async def on_disconnect():
    logger.info('Bot disconnected.')


@bot.event
async def on_ready():
    logger.info('Bot ready.')
    if bool(os.environ.get('RESEND_INTRO', False)):
        logger.info('Resetting verification channel')
        channel = await interactions.get(bot, interactions.Channel, object_id=channel_id)
        try:
            async for m in channel.history():
                await m.delete()
        except IndexError:
            pass
        await channel.send(
            'Welcome! Please accept the server rules, then press the button below.',
            components=[
                interactions.Button(
                    style=interactions.ButtonStyle.PRIMARY,
                    label="Verify your membership",
                    custom_id='verify_button'
                )
            ])


@bot.component('verify_button')
async def on_verify_button(ctx: interactions.ComponentContext):
    logger.info(f'Verify button pressed by {ctx.member}')
    modal = interactions.Modal(
        title='Verification',
        custom_id='verify_modal',
        components=[
            interactions.TextInput(
                style=interactions.TextStyleType.SHORT,
                label='Unite the Union member number',
                min_length=8,
                max_length=8,
                custom_id='unite_id'
            ),
            interactions.TextInput(
                style=interactions.TextStyleType.SHORT,
                label="Are you a manager? Put 'Y' or 'N'",
                min_length=1,
                max_length=1,
                custom_id='is_manager',
            ),
        ]
    )
    await ctx.popup(modal)


@bot.modal('verify_modal')
async def on_verify_modal(ctx: interactions.ComponentContext, unite_id_s: str, is_manager_s: str):
    logger.info(f'Verify modal completed by {ctx.member}: id={unite_id_s}, m={is_manager_s}')
    unite_id = int(unite_id_s)
    is_manager = is_manager_s.lower() == 'y'
    if not link_member(ctx.member, unite_id):
        logger.info(f'Verification failed for {unite_id}')
        await set_roles(ctx.member, {
            verified_role_id: False,
            manager_role_id: False,
            ic_role_id: False,
        })
        await ctx.send(
            f"We can't find your member number {unite_id} on the list yet, "
            "please double check and try again or "
            f"ping <@{os.environ['DISCORD_ADMIN_USER_ID']}> with your member number "
            "and corp username",
            ephemeral=True,
        )
        return

    await ctx.send('Success!', ephemeral=True)
    logger.info(f'Verification succeeded for {unite_id}')
    await set_roles(ctx.member, {
        verified_role_id: True,
        manager_role_id: is_manager,
        ic_role_id: not is_manager
    })


async def set_roles(member: interactions.Member, roles: Dict[int, bool]):
    for role_id, present in roles.items():
        if present:
            if role_id not in member.roles:
                await member.add_role(role_id)
        else:
            if role_id in member.roles:
                await member.remove_role(role_id)


logger.info('Bot starting...')
bot.start()
logger.info('Bot stopped. Bye.')
