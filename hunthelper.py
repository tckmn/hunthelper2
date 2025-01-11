#!/usr/bin/env python3

from aiohttp import web
from datetime import datetime
import asyncio
import discord
import json
import pickle
import requests
import time

CONFIG = lambda: type('config_object', (), json.load(open('config.json')))

D = 'discord'
W = 'web'
B = 'backend'
C = 3
H = 2
M = 1
L = 0

normalize = lambda name: ''.join(ch if ch.isalpha() or ch.isdigit() else
                                 '-' if ch == ' ' or ch == '-' else
                                 '' for ch in name.lower()) or name
metafy = lambda name: f'[META] {name[1:].strip()}' if name[0] == '#' else name
demetafy = lambda name: f'{name[1:].strip()}' if name[0] == '#' else name
fixify = lambda url, is_meta: url.replace('puzzle', 'round') if is_meta else url
fixify = lambda url, is_meta: url

class NormDict:
    def __init__(self):
        self.underlying = dict()

    def contains(self, k): return normalize(k) in self.underlying
    def get(self, k, k2):
        v = self.underlying.get(normalize(k), dict())
        return v[k2] if k2 in v else None
    def set(self, k, v):
        self.underlying[normalize(k)] = v
    def move(self, korig, knew):
        if normalize(korig) == normalize(knew): return
        self.underlying[normalize(knew)] = self.underlying[normalize(korig)]
        del self.underlying[normalize(korig)]

    def __getstate__(self): return self.__dict__
    def __setstate__(self, d): self.__dict__ = d

class HuntHelper():
    def __init__(self):
        self.puzzles = NormDict()
        self.drive_token = ''
        self.drive_expires = 0
        self.solvecount = 0
        self.solvecategory = None

    def init(self):
        intents = discord.Intents.default()
        intents.members = True
        self.client = discord.Client(intents=intents)
        self.client.event(self.on_member_join)
        self.client.event(self.on_ready)
        self.client.event(self.on_message)

    def __getstate__(self):
        return {
            'puzzles': self.puzzles,
            'drive_token': self.drive_token,
            'drive_expires': self.drive_expires,
            'solvecount': self.solvecount,
            'solvecategory': self.solvecategory
        }
    def __setstate__(self, d): self.__dict__ = d

    async def log(self, src, lvl, x):
        msg = f'[{src}] {"WARNING: " if lvl == C else ""}{x}'
        if lvl >= L:
            timestamped = datetime.now().strftime('%F %T - ') + msg
            print(timestamped)
            with open('log', 'a') as f: f.write(timestamped + '\n')
        if lvl >= M: pass
        if lvl >= H: await self.discord_log.send(msg + (f' <@{CONFIG().discord_pingid}>' if lvl == C else ''))

    def drivelink(self, name, override=None): return f'https://docs.google.com/spreadsheets/d/{override or self.puzzles.get(name, "drive")}/edit'
    def puzlink(self, name): return fixify(CONFIG().puzprefix, name[0] == '#') + normalize(demetafy(name))
    def links(self, name): return { 'drive': self.drivelink(name), 'puzzle': self.puzlink(name) }

    async def on_member_join(self, member):
        await self.log(D, H, 'adding new member role')
        await member.add_roles(discord.Object(CONFIG().discord_role))

    async def on_ready(self):
        self.discord_log = self.client.get_channel(CONFIG().discord_log)
        self.discord_announce = self.client.get_channel(CONFIG().discord_announce)
        self.discord_guild = self.client.get_guild(CONFIG().discord_guild)
        await self.log(D, H, 'started')

    async def on_message(self, msg):
        if msg.author.id == CONFIG().discord_admin and msg.channel.id == CONFIG().discord_log:
            exec(f'async def tmp(self): return {msg.content}', globals())
            await msg.reply(f'```\n{await tmp(self)}\n```')

    async def make_puzzle(self, name, rnd):
        is_round = name[0] == '#'
        truename = metafy(name)

        if is_round:
            drive_parent = await self.create_drive(name[1:].strip(), 'folder', CONFIG().drive_root)
            discord_parent = await self.discord_guild.create_category_channel(name[1:].strip())
            # for some reason passing position= to create_category_channel directly does something extremely confusing and nonsensical
            await discord_parent.edit(position=self.client.get_channel(CONFIG().discord_position).position+1)
        else:
            for _ in range(5):
                if self.puzzles.contains(rnd): break
                await self.log(B, H, 'round does not exist, waiting 2s...')
                await asyncio.sleep(2)
            else:
                await self.log(B, C, 'still not there, bailing out')
                raise Exception()
            drive_parent = self.puzzles.get(rnd, '^drive')
            discord_parent = self.client.get_channel(self.puzzles.get(rnd, '^discord'))

        drive = await self.create_drive(truename, 'spreadsheet', drive_parent)
        discord = await self.discord_guild.create_text_channel(truename.replace('[META] ', 'ᴹᴱᵀᴬ-'), category=discord_parent, topic=f'{self.puzlink(name)} | {self.drivelink(None, drive)}')

        return {
            'drive': drive,
            'discord': discord.id,
            **({
                '^drive': drive_parent,
                '^discord': discord_parent.id
            } if is_round else {})
        }

    async def mark_solved(self, name):
        if self.solvecount % 50 == 0:
            self.solvecategory = (await self.discord_guild.create_category_channel(f'solved puzzles {(self.solvecount//50)+1}')).id

        await self.client.get_channel(self.puzzles.get(name, 'discord')).edit(category=self.client.get_channel(self.solvecategory))
        self.solvecount += 1

        await self.drive_check_token()
        requests.patch(f'https://www.googleapis.com/drive/v3/files/{self.puzzles.get(name, "drive")}', json={
            'name': f'[SOLVED] {metafy(name)}'
        }, headers={
            'Authorization': f'Bearer {self.drive_token}'
        })

    async def create_drive(self, name, mime, parent):
        await self.drive_check_token()
        resp = requests.post('https://www.googleapis.com/drive/v3/files', json={
            'name': name,
            'mimeType': 'application/vnd.google-apps.' + mime,
            'parents': [parent]
        }, headers={
            'Authorization': f'Bearer {self.drive_token}'
        })
        await self.log(B, L, f'req create_drive {resp} {resp.text.replace(chr(10), " ")}')
        await self.log(B, H, f'created drive {mime}: {name} ({resp.status_code})')
        try:
            return json.loads(resp.text)['id']
        except:
            await self.log(B, C, 'failed!')
            return 'FAILED'

    async def drive_check_token(self):
        if self.drive_expires < time.time() + 10:
            resp = requests.post('https://oauth2.googleapis.com/token', {
                'client_id': CONFIG().drive_client_id,
                'client_secret': CONFIG().drive_client_secret,
                'refresh_token': CONFIG().drive_refresh_token,
                'grant_type': 'refresh_token'
            })
            await self.log(B, L, f'req drive_check_token {resp} {resp.text.replace(chr(10), " ")}')
            resp = json.loads(resp.text)
            self.drive_token = resp['access_token']
            self.drive_expires = time.time() + resp['expires_in']

    async def handler(self, data):
        action = data.get('action')
        name = data.get('name')
        rnd = data.get('round')

        if action == 'fetch':
            if not self.puzzles.contains(name):
                await self.log(W, H, f'creating puzzle {name}')
                self.puzzles.set(name, await self.make_puzzle(name, rnd))
            return {
                **self.links(name)
            }

        elif action == 'rename':
            oldname = data['oldname']
            if oldname == name:
                await self.log(W, H, f'no-op rename of {name}, delegating to fetch')
                data['action'] = 'fetch'
                return await self.handler(data)
            if not self.puzzles.contains(oldname):
                await self.log(W, C, f'renaming nonexistent {oldname} to {name}')
                self.puzzles.set(name, await self.make_puzzle(name, rnd))
            else:
                await self.log(W, C, f'renaming {oldname} to {name}')
                self.puzzles.move(oldname, name)
            return {
                **self.links(name),
                'note': f'{datetime.now()}: renamed from {oldname} to {name}'
            }

        elif action == 'solve':
            await self.discord_announce.send(f'Puzzle *{metafy(name)}* solved with answer **{data["ans"]}**! :tada: https://discord.com/channels/{CONFIG().discord_guild}/{self.puzzles.get(name, "discord")}')
            await self.mark_solved(name)
            return {}

        else:
            await self.log(W, C, f'unknown action??? {action}')
            return {
                'note': f'{datetime.now()}: something extremely confusing and bad happened'
            }

    async def handler_wrap(self, req):
        if req.method != 'POST' or req.path != CONFIG().path: raise web.HTTPNotFound()
        data = await req.json()
        await self.log(W, M, json.dumps(data))
        resp = json.dumps(await self.handler(data))
        pickle.dump(helper, open('helperdata', 'wb'))
        return web.Response(text=resp)

    async def backend(self):
        server = web.Server(self.handler_wrap)
        runner = web.ServerRunner(server)
        await runner.setup()
        site = web.TCPSite(runner, '', CONFIG().port)
        await site.start()
        await self.log(W, M, 'started')

    async def main(self):
        await asyncio.gather(
            self.client.start(CONFIG().discord_bot),
            self.backend()
        )

try:    helper = pickle.load(open('helperdata', 'rb'))
except: helper = HuntHelper()
helper.init()
asyncio.get_event_loop().run_until_complete(helper.main())
