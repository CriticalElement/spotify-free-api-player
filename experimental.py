import browser_cookie3
import requests
import websockets
import asyncio
import json
import logging
import string
import random

from threading import Thread
from requests.exceptions import RequestException

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)-8s - %(name)-14s - %(message)s')


class SpotifyPlayer:
    pause = {'command': {'endpoint': 'pause'}}
    resume = {'command': {'endpoint': 'resume'}}
    skip = {'command': {'endpoint': 'skip_next'}}
    previous = {'command': {'endpoint': 'skip_prev'}}
    shuffle = {'command': {'value': True, 'endpoint': 'set_shuffling_context'}}
    stop_shuffle = {'command': {'value': False, 'endpoint': 'set_shuffling_context'}}
    repeating_context = {'command': {'repeating_context': True, 'repeating_track': False, 'endpoint': 'set_options'}}
    repeating_track = {'command': {'repeating_context': True, 'repeating_track': True, 'endpoint': 'set_options'}}
    no_repeat = {'command': {'repeating_context': False, 'repeating_track': False, 'endpoint': 'set_options'}}

    @staticmethod
    def volume(volume):
        return {'volume': volume * 65535 / 100, 'url': 'https://guc-spclient.spotify.com/connect-state/'
                                                'v1/connect/volume/from/player/to/device',
                'request_type': 'PUT'}

    @staticmethod
    def seek_to(ms):
        return {'command': {'value': ms, 'endpoint': 'seek_to'}}

    @staticmethod
    def add_to_queue(track_id):
        return {'command': {'track': {'uri': f'spotify:track:{track_id}', 'metadata': {'is_queued': True},
                                      'provider': 'queue'}, 'endpoint': 'add_to_queue'}}

    def remove_from_queue(self, track_id):
        matches = ([index for index, track in enumerate(self.queue) if track_id in track['uri']
                    or 'spotify:ad:' in track['uri']])
        [self.queue.pop(index) for index in matches]
        return {'command': {'next_tracks': self.queue, 'queue_revision': self.queue_revision, 'endpoint': 'set_queue'}}

    @staticmethod
    def play(track_id):
        return [{'command': {'track': {'uri': f'spotify:track:{track_id}', 'metadata': {'is_queued': True},
                                       'provider': 'queue'}, 'endpoint': 'add_to_queue'}},
                {'command': {'endpoint': 'skip_next'}}]

    def __init__(self):
        self.cj = browser_cookie3.chrome()
        self._default_headers = {'sec-fetch-dest': 'empty',
                                 'sec-fetch-mode': 'cors',
                                 'sec-fetch-site': 'same-origin',
                                 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                               '(KHTML, like Gecko) Chrome/87.0.4280.66 Safari/537.36'}

        self._session = requests.Session()
        self._authorize()

    def _authorize(self):
        access_token_headers = self._default_headers.copy()
        access_token_headers.update({'spotify-app-version': '1.1.48.530.g38509c6c'})

        access_token_url = 'https://open.spotify.com/get_access_token?reason=transport&productType=web_player'

        response = self._session.get(access_token_url, headers=access_token_headers, cookies=self.cj)
        access_token_response = response.json()
        self.access_token = access_token_response['accessToken']
        self.access_token_expire = access_token_response['accessTokenExpirationTimestampMs']
        self.cj._cookies['.spotify.com']['/']['sp_t'] = response.cookies

        guc_url = f'wss://guc-dealer.spotify.com/?access_token={self.access_token}'
        guc_headers = {'Accept-Encoding': 'gzip, deflate, br',
                       'Accept-Language': 'en-US,en,q=0.9',
                       'Cache-Control': 'no-cache',
                       'Connection': 'upgrade',
                       'Host': 'guc-dealer.spotify.com',
                       'Origin': 'https://open.spotify.com',
                       'Pragma': 'no-cache',
                       'Sec-WebSocket-Extensions': 'permessage-deflate; client_max_window_bits',
                       'Sec-WebSocket-Key': 'randomkey',
                       'Sec-WebSocket-Version': '13',
                       'Upgrade': 'websocket',
                       'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'
                                     ' Chrome/87.0.4280.66 Safari/537.36'}

        self.connection_id = None
        self.queue_revision = None

        async def websocket():
            async with websockets.connect(guc_url, extra_headers=guc_headers) as ws:
                Thread(target=lambda: start_ping_loop(ws)).start()
                while True:
                    recv = await ws.recv()
                    load = json.loads(recv)
                    if load.get('headers'):
                        if load['headers'].get('Spotify-Connection-Id'):
                            self.connection_id = load['headers']['Spotify-Connection-Id']
                    if load.get('payloads'):
                        if load['payloads'][0].get('cluster'):
                            self.queue = load['payloads'][0]['cluster']['player_state']['next_tracks']
                            self.queue_revision = load['payloads'][0]['cluster']['player_state']['queue_revision']

        def start_ping_loop(ws):
            asyncio.new_event_loop().run_until_complete(ping_loop(ws))

        async def ping_loop(ws):
            while True:
                await ws.send('{"type": "ping"}')
                await asyncio.sleep(30)

        Thread(target=lambda: asyncio.new_event_loop().run_until_complete(websocket())).start()

        device_url = 'https://guc-spclient.spotify.com/track-playback/v1/devices'
        self.device_id = ''.join(random.choices(string.ascii_letters, k=40))
        while True:
            if self.connection_id:
                device_data = {"device": {"brand": "spotify", "capabilities":
                                          {"change_volume": True, "enable_play_token": True,
                                           "supports_file_media_type": True,
                                           "play_token_lost_behavior": "pause",
                                           "disable_connect": True, "audio_podcasts": True,
                                           "video_playback": True,
                                           "manifest_formats": ["file_urls_mp3",
                                                                "manifest_ids_video",
                                                                "file_urls_external",
                                                                "file_ids_mp4",
                                                                "file_ids_mp4_dual"]},
                                          "device_id": self.device_id, "device_type": "computer",
                                          "metadata": {}, "model": "web_player", "name": "Spotify Player",
                                          "platform_identifier": "web_player windows 10;chrome 87.0.4280.66;desktop"},
                               "connection_id": self.connection_id, "client_version": "harmony:4.11.0-af0ef98",
                               "volume": 65535}
                break

        device_headers = {'authority': 'guc-spclient.spotify.com',
                          'method': 'POST',
                          'path': '/track-playback/v1/devices',
                          'scheme': 'https',
                          'accept': '*/*',
                          'accept-encoding': 'gzip, deflate, br',
                          'accept-language': 'en-US,en;q=0.9',
                          'authorization': f'Bearer {self.access_token}',
                          'content-type': 'application/json',
                          'origin': 'https://open.spotify.com',
                          'referer': 'https://open.spotify.com/',
                          'sec-fetch-dest': 'empty',
                          'sec-fetch-mode': 'cors',
                          'sec-fetch-site': 'same-site',
                          'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                        '(KHTML, like Gecko) Chrome/87.0.4280.66 Safari/537.36'}

        response = self._session.post(device_url, headers=device_headers, data=json.dumps(device_data))
        if response.status_code == 200:
            logging.log(logging.INFO, f'Successfully created Spotify device with id {self.device_id}.')

        notifications_url = f'https://api.spotify.com/v1/me/notifications/user?connection_id={self.connection_id}'
        notifications_headers = self._default_headers.copy()
        notifications_headers.update({'Authorization': f'Bearer {self.access_token}'})
        self._session.put(notifications_url, headers=notifications_headers)

        hobs_url = f'https://guc-spclient.spotify.com/connect-state/v1/devices/hobs_{self.device_id}'
        hobs_headers = self._default_headers.copy()
        hobs_headers.update({'authorization': f'Bearer {self.access_token}'})
        hobs_headers.update({'x-spotify-connection-id': self.connection_id})
        hobs_data = {"member_type": "CONNECT_STATE", "device": {"device_info":
                                                                {"capabilities": {"can_be_player": False,
                                                                                  "hidden": True}}}}
        response = self._session.put(hobs_url, headers=hobs_headers, data=json.dumps(hobs_data))
        self.queue = response.json()['player_state']['next_tracks']
        self.queue_revision = response.json()['player_state']['queue_revision']

    def command(self, command_dict):
        headers = {'Authorization': f'Bearer {self.access_token}'}
        currently_playing_device = self._session.get('https://api.spotify.com/v1/me/player', headers=headers)
        try:
            currently_playing_device = currently_playing_device.json()['device']['id']
        except json.decoder.JSONDecodeError:
            currently_playing_device = self._session.get('https://api.spotify.com/v1/me/player/devices',
                                                         headers=headers).json()['devices'][0]['id']
            # There are still some bugs
        player_url = f'https://guc-spclient.spotify.com/connect-state/v1/player/command/from/{self.device_id}' \
                     f'/to/{currently_playing_device}'
        if isinstance(command_dict, list):
            for command in command_dict:
                player_data = command
                player_headers = self._default_headers.copy()
                player_headers.update({'authorization': f'Bearer {self.access_token}'})
                response = self._session.post(player_url, headers=headers, data=json.dumps(player_data))
                if response.status_code != 200:
                    raise RequestException(f'Command failed: {response.json()}')
                else:
                    logging.log(logging.INFO, 'Command executed successfully.')
        else:
            if 'url' in command_dict:
                player_url = command_dict['url'].replace('player', self.device_id).replace('device',
                                                                                           currently_playing_device)
                command_dict.pop('url')
            player_data = command_dict
            player_headers = self._default_headers.copy()
            player_headers.update({'authorization': f'Bearer {self.access_token}'})
            if 'request_type' in player_data:
                if player_data['request_type'] == 'PUT':
                    player_data.pop('request_type')
                    response = self._session.put(player_url, headers=headers, data=json.dumps(player_data))
                    if response.status_code != 200:
                        try:
                            response.json()
                            raise RequestException(f'Command failed: {response.json()}')
                        except json.decoder.JSONDecodeError:
                            pass
                    else:
                        logging.log(logging.INFO, 'Command executed successfully.')
            else:
                response = self._session.post(player_url, headers=headers, data=json.dumps(player_data))
                if response.status_code != 200:
                    try:
                        response.json()
                        raise RequestException(f'Command failed: {response.json()}')
                    except json.decoder.JSONDecodeError:
                        pass
                else:
                    logging.log(logging.INFO, 'Command executed successfully.')
