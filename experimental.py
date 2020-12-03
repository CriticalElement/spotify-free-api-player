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
        return {'volume': volume}

    @staticmethod
    def seek_to(ms):
        return {'command': {'value': ms, 'endpoint': 'seek_to'}}

    @staticmethod
    def add_to_queue(track_id):
        return {'command': {'track': {'uri': f'spotify:track:{track_id}', 'metadata': {'is_queued': True},
                                      'provider': 'queue'}, 'endpoint': 'add_to_queue'}}

    @staticmethod
    def play(track_id):
        pass

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

        async def websocket():
            async with websockets.connect(guc_url, extra_headers=guc_headers) as ws:
                while True:
                    recv = await ws.recv()
                    if json.loads(recv).get('headers'):
                        if json.loads(recv)['headers'].get('Spotify-Connection-Id'):
                            self.connection_id = json.loads(recv)['headers']['Spotify-Connection-Id']
                    await asyncio.sleep(30) # TODO: Fix this garbage
                    await ws.send('{"type": "ping"}')

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
        player_data = command_dict
        player_headers = self._default_headers.copy()
        player_headers.update({'authorization': f'Bearer {self.access_token}'})
        response = self._session.post(player_url, headers=headers, data=json.dumps(player_data))
        if response.status_code != 200:
            raise RequestException(f'Command failed: {response.json()}')
