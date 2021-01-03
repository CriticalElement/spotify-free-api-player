import browser_cookie3
import requests
import websockets
import asyncio
import json
import logging
import string
import random
import time
import typing

from threading import Thread
from requests.exceptions import RequestException


class SpotifyPlayer:
    pause = {'command': {'endpoint': 'pause'}}
    resume = {'command': {'endpoint': 'resume'}}
    skip = {'command': {'endpoint': 'skip_next'}}
    previous = {'command': {'endpoint': 'skip_prev'}}
    repeating_context = {'command': {'repeating_context': True, 'repeating_track': False, 'endpoint': 'set_options'}}
    repeating_track = {'command': {'repeating_context': True, 'repeating_track': True, 'endpoint': 'set_options'}}
    no_repeat = {'command': {'repeating_context': False, 'repeating_track': False, 'endpoint': 'set_options'}}
    shuffle = {'command': {'value': True, 'endpoint': 'set_shuffling_context'}}
    stop_shuffle = {'command': {'value': False, 'endpoint': 'set_shuffling_context'}}

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

    @staticmethod
    def play(track_id):
        return {"command": {"context": {"uri": f"spotify:track:{track_id}",
                                        "url": f"context://spotify:track:{track_id}",
                                        "metadata": {}}, "play_origin":
                            {"feature_identifier": "harmony", "feature_version": "4.11.0-af0ef98"}, "options":
                            {"license": "on-demand", "skip_to": {"track_index": 0}, "player_options_override": {}},
                            "endpoint": "play"}}

    def remove_from_queue(self, track_id):
        matches = ([index for index, track in enumerate(self.queue) if track_id in track['uri']
                    or 'spotify:ad:' in track['uri']])
        [self.queue.pop(index) for index in matches]
        return {'command': {'next_tracks': self.queue, 'queue_revision': self.queue_revision, 'endpoint': 'set_queue'}}

    def clear_queue(self):
        matches = ([track for track in self.queue if 'queue' != track['provider']])
        return {'command': {'next_tracks': matches, 'queue_revision': self.queue_revision, 'endpoint': 'set_queue'}}

    def queue_playlist(self, playlist_id):
        url = f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks'
        headers = {'Authorization': f'Bearer {self.access_token}'}
        response = self._session.get(url, headers=headers)
        ids = [item['track']['id'] for item in response.json()['items']]
        queue = [{'uri': f'spotify:track:{track_id}', 'metadata': {'is_queued': True}, 'provider': 'queue'}
                 for track_id in ids]
        if self.shuffling:
            random.shuffle(queue)
        queuequeue = [track for track in self.queue if track['provider'] != 'context']
        queue = queuequeue + queue
        if ids:
            return {'command': {'next_tracks': queue, 'queue_revision': self.queue_revision, 'endpoint': 'set_queue'}}

    def play_playlist(self, playlist_id, skip_to=0):
        url = f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks'
        headers = {'Authorization': f'Bearer {self.access_token}'}
        response = self._session.get(url, headers=headers)
        ids = [item['track']['id'] for item in response.json()['items']]
        queue = [{'uri': f'spotify:track:{track_id}', 'metadata': {'is_queued': True}, 'provider': 'queue'}
                 for track_id in ids]
        if self.shuffling:
            random.shuffle(queue)
        queue = queue + self.queue
        if ids:
            return [{'command': {'next_tracks': queue[1:], 'queue_revision': self.queue_revision,
                                 'endpoint': 'set_queue'}},
                    {"command": {"context": {"uri": f"{queue[0]['uri']}",
                                             "url": f"context://{queue[0]['uri']}",
                                             "metadata": {}}, "play_origin":
                                 {"feature_identifier": "harmony", "feature_version": "4.11.0-af0ef98"}, "options":
                                 {"license": "on-demand", "skip_to": {"track_index": skip_to},
                                  "player_options_override": {}},
                                 "endpoint": "play"}}]

    def queue_from_uris(self, uris):
        queue = [{'uri': uri, 'metadata': {'is_queued': True}, 'provider': 'queue'}
                 for uri in uris]
        queuequeue = [track for track in self.queue if track['provider'] != 'context']
        queue = queuequeue + queue
        return {'command': {'next_tracks': queue, 'queue_revision': self.queue_revision,
                            'endpoint': 'set_queue'}}

    def play_from_uris(self, uris):
        queue = [{'uri': uri, 'metadata': {'is_queued': True}, 'provider': 'queue'}
                 for uri in uris]
        queue = queue + self.queue
        return [{'command': {'next_tracks': queue[1:], 'queue_revision': self.queue_revision,
                             'endpoint': 'set_queue'}},
                {"command": {"context": {"uri": queue[0]['uri'],
                                         "url": f'context://{queue[0]["uri"]}',
                                         "metadata": {}}, "play_origin":
                             {"feature_identifier": "harmony", "feature_version": "4.11.0-af0ef98"}, "options":
                             {"license": "on-demand", "skip_to": {"track_index": 0}, "player_options_override": {}},
                             "endpoint": "play"}}]

    def play_from_context(self, context_uri, skip_to=0):
        oldqueue = [track for track in self.queue if track['provider'] == 'queue']
        oldqueue = [{'uri': track['uri'], 'metadata': {'is_queued': True}, 'provider': 'queue'}
                    for track in oldqueue]
        self.command(self.clear_queue())
        self.command({"command": {"context": {"uri": f"{context_uri}",
                                              "url": f"context://{context_uri}",
                                              "metadata": {}}, "play_origin":
                                  {"feature_identifier": "harmony", "feature_version": "4.11.0-af0ef98"}, "options":
                                  {"license": "on-demand", "skip_to": {"track_index": skip_to},
                                   "player_options_override": {}},
                                  "endpoint": "play"}})
        time.sleep(0.75)
        context_songs = [track for track in self.queue if track['provider'] == 'context']
        context_songs = [track for track in context_songs if track['metadata']['iteration'] == '0']
        context_songs = [{'uri': track['uri'], 'metadata': {'is_queued': True}, 'provider': 'queue'}
                         for track in context_songs]
        queue = context_songs + oldqueue
        return {'command': {'next_tracks': queue, 'queue_revision': self.queue_revision,
                            'endpoint': 'set_queue'}}

    def queue_from_context(self, context_uri, skip_to=0):
        oldqueue = [track for track in self.queue if track['provider'] == 'queue']
        oldqueue = [{'uri': track['uri'], 'metadata': {'is_queued': True}, 'provider': 'queue'}
                    for track in oldqueue]
        self.command(self.clear_queue())
        self.command({"command": {"context": {"uri": f"{context_uri}",
                                              "url": f"context://{context_uri}",
                                              "metadata": {}}, "play_origin":
                                  {"feature_identifier": "harmony", "feature_version": "4.11.0-af0ef98"}, "options":
                                  {"license": "on-demand", "skip_to": {"track_index": skip_to},
                                   "player_options_override": {}},
                                  "endpoint": "play"}})
        time.sleep(0.75)
        context_songs = [track for track in self.queue if track['provider'] == 'context']
        context_songs = [track for track in context_songs if track['metadata']['iteration'] == '0']
        context_songs = [{'uri': track['uri'], 'metadata': {'is_queued': True}, 'provider': 'queue'}
                         for track in context_songs]
        queue = context_songs + oldqueue
        return {'command': {'next_tracks': queue, 'queue_revision': self.queue_revision,
                            'endpoint': 'set_queue'}}

    def __init__(self, event_reciever: typing.List[typing.Callable] = None):
        if event_reciever is None:
            event_reciever = [lambda: None]
        self.isinitialized = False
        try:
            self.cj = browser_cookie3.chrome()
            # noinspection PyProtectedMember
            _ = self.cj._cookies['.spotify.com']['/']['sp_t']
            self.isinitialized = True
        except Exception as e:
            logging.error(e, exc_info=True)
        self._default_headers = {'sec-fetch-dest': 'empty',
                                 'sec-fetch-mode': 'cors',
                                 'sec-fetch-site': 'same-origin',
                                 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                               '(KHTML, like Gecko) Chrome/87.0.4280.66 Safari/537.36'}

        self._session = requests.Session()
        self.event_reciever = event_reciever
        self.shuffling = False
        self.looping = False
        self.playing = False
        self.current_volume = 65535
        self.timestamp = 0
        self._last_timestamp = 0
        self.position_ms = 0
        self._last_position = 0
        self.last_command = None
        self.time_executed = 0
        self.ping = False
        self.running_pings = False
        self.event_loop = None
        self.ws = None
        if self.isinitialized:
            self._authorize()

    def _authorize(self):
        if self.running_pings:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.event_loop)
        access_token_headers = self._default_headers.copy()
        access_token_headers.update({'spotify-app-version': '1.1.48.530.g38509c6c'})

        access_token_url = 'https://open.spotify.com/get_access_token?reason=transport&productType=web_player'
        self._session = requests.Session()
        response = self._session.get(access_token_url, headers=access_token_headers, cookies=self.cj)
        access_token_response = response.json()
        self.access_token = access_token_response['accessToken']
        self.access_token_expire = access_token_response['accessTokenExpirationTimestampMs'] / 1000 + time.time()

        guc_url = f'wss://guc-dealer.spotify.com/?access_token={self.access_token}'
        guc_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'
                                     ' Chrome/87.0.4280.66 Safari/537.36'}

        self.connection_id = None
        self.queue_revision = None

        async def websocket():
            async with websockets.connect(guc_url, extra_headers=guc_headers) as ws:
                self.ping = True
                self.ws = ws
                if not self.running_pings:
                    Thread(target=lambda: start_ping_loop()).start()
                while True:
                    try:
                        self.isinitialized = True
                        recv = await ws.recv()
                        load = json.loads(recv)
                        if load.get('headers'):
                            if load['headers'].get('Spotify-Connection-Id'):
                                self.connection_id = load['headers']['Spotify-Connection-Id']
                        if load.get('payloads'):
                            try:
                                if load['payloads'][0].get('cluster'):
                                    try:
                                        self.queue = load['payloads'][0]['cluster']['player_state']['next_tracks']
                                    except KeyError:
                                        pass
                                    self.queue_revision = (load['payloads'][0]['cluster']['player_state']
                                                           ['queue_revision'])
                                    options = load['payloads'][0]['cluster']['player_state']['options']
                                    try:
                                        active_device = load['payloads'][0]['cluster']['active_device_id']
                                        self.current_volume = (load['payloads'][0]['cluster']['devices'][active_device]
                                                               ['volume'])
                                    except KeyError:
                                        pass
                                    self.playing = not load['payloads'][0]['cluster']['player_state']['is_paused']
                                    self.shuffling = options['shuffling_context']
                                    self._last_timestamp = self.timestamp
                                    self.timestamp = int(load['payloads'][0]['cluster']['player_state']['timestamp'])
                                    self._last_position = self.position_ms
                                    position_ms = int(load['payloads'][0]['cluster']['player_state']
                                                      ['position_as_of_timestamp'])

                                    time_executed = time.time()
                                    if time_executed - self.time_executed < 0.7:
                                        if self.last_command.get('command'):
                                            whitelist = ['seek_to', 'play', 'skip_next', 'skip_prev']
                                            if self.last_command['command']['endpoint'] not in whitelist:
                                                if abs(position_ms - self._last_position) > 500:
                                                    self.position_ms = self._last_position
                                            else:
                                                self.position_ms = position_ms
                                    else:
                                        self.position_ms = position_ms
                                    if options['repeating_track']:
                                        self.looping = 'track'
                                    elif options['repeating_context']:
                                        self.looping = 'context'
                                    else:
                                        self.looping = 'off'
                                    [event() for event in self.event_reciever]
                            except AttributeError:
                                pass
                    except websockets.exceptions.ConnectionClosedError as exc:
                        logging.error(exc, exc_info=False)
                        self.isinitialized = False
                        break

        def start_ping_loop():
            asyncio.new_event_loop().run_until_complete(ping_loop())

        async def ping_loop():
            self.running_pings = True
            while self.ping:
                if self.access_token_expire < time.time():
                    self._authorize()
                    while not self.isinitialized:
                        pass
                if self.ping:
                    await self.ws.send('{"type": "ping"}')
                await asyncio.sleep(30)

        if not self.event_loop:
            self.event_loop = asyncio.new_event_loop()
        else:
            self.event_loop = asyncio.get_event_loop()
        Thread(target=lambda: self.event_loop.run_until_complete(websocket())).start()

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
                               "connection_id": self.connection_id, "client_version":
                               "harmony:4.11.0-af0ef98",
                               "volume": 65535}
                break

        device_headers = self._default_headers.copy()
        device_headers.update({'authorization': f'Bearer {self.access_token}'})

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
        try:
            self.queue = response.json()['player_state']['next_tracks']
        except KeyError:
            self.queue = []
        response_load = response.json()
        response_options = response_load['player_state']['options']
        try:
            active_device_id = response_load['active_device_id']
            self.current_volume = response_load['devices'][active_device_id]['volume']
        except KeyError:
            pass
        self.queue_revision = response_load['player_state']['queue_revision']
        self.shuffling = response_options['shuffling_context']
        self.playing = not response_load['player_state']['is_paused']
        self._last_position = int(response_load['player_state']['position_as_of_timestamp'])
        self._last_timestamp = int(response_load['player_state']['timestamp'])
        self.timestamp = int(response_load['player_state']['timestamp'])
        self.position_ms = int(response_load['player_state']['position_as_of_timestamp'])
        if response_options['repeating_track']:
            self.looping = 'track'
        elif response_options['repeating_context']:
            self.looping = 'context'
        else:
            self.looping = 'off'

        def progress_loop():

            def recalibrate():
                while True:
                    time.sleep(1)
                    recalibrate_response = self._session.get('https://api.spotify.com/v1/me/player/currently-playing',
                                                             headers={'Authorization': f'Bearer {self.access_token}'})
                    if recalibrate_response.status_code == 200:
                        self.position_ms = recalibrate_response.json()['progress_ms']

            Thread(target=recalibrate).start()

            while True:
                time.sleep(0.5)
                if self.playing:
                    self._last_timestamp = self.timestamp
                    self.timestamp = self.timestamp + 500
                    self._last_position = self.position_ms
                    diff = self.timestamp / 1000 - self._last_timestamp / 1000
                    self.position_ms = self._last_position / 1000 + diff
                    self.position_ms = self.position_ms * 1000
                else:
                    self._last_timestamp = self.timestamp
                    self._last_position = self.position_ms
                    diff = self.timestamp / 1000 - self._last_timestamp / 1000
                    self.position_ms = self._last_position / 1000 + diff
                    self.position_ms = self.position_ms * 1000

        if self.queue:
            Thread(target=progress_loop).start()

    def transfer(self, device_id):
        if self.access_token_expire < time.time():
            self._authorize()
            while not self.isinitialized:
                pass
        transfer_url = f'https://guc-spclient.spotify.com/connect-state/v1/connect/transfer/from/' \
                       f'{self.device_id}/to/{device_id}'
        transfer_headers = self._default_headers.copy()
        transfer_headers.update({'authorization': f'Bearer {self.access_token}'})
        transfer_data = {'transfer_options': {'restore_paused': 'restore'}}
        response = self._session.post(transfer_url, headers=transfer_headers, data=json.dumps(transfer_data))
        return response

    def add_event_reciever(self, event_reciever: typing.Callable):
        self.event_reciever.append(event_reciever)

    def remove_event_reciever(self, event_reciever: typing.Callable):
        if event_reciever in self.event_reciever:
            self.event_reciever.pop(self.event_reciever.index(event_reciever))
        else:
            raise TypeError('The specified event reciever was not in the list of event recievers.')

    def command(self, command_dict):
        if self.access_token_expire < time.time():
            self._authorize()
            while not self.isinitialized:
                pass
        headers = {'Authorization': f'Bearer {self.access_token}'}
        currently_playing_device = self._session.get('https://api.spotify.com/v1/me/player', headers=headers)
        try:
            currently_playing_device = currently_playing_device.json()['device']['id']
        except json.decoder.JSONDecodeError:
            currently_playing_device = self._session.get('https://api.spotify.com/v1/me/player/devices',
                                                         headers=headers).json()['devices'][0]['id']
            self.transfer(currently_playing_device)
            time.sleep(1)
            currently_playing_device = self._session.get('https://api.spotify.com/v1/me/player', headers=headers)
            currently_playing_device = currently_playing_device.json()['device']['id']
        except requests.exceptions.RequestException:
            self._authorize()
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
                    logging.log(logging.INFO, f'Command executed successfully. {player_data}')
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
                            raise RequestException(f'Command failed: {response.json()}')
                        except json.decoder.JSONDecodeError:
                            raise RequestException(f'Command failed.')
                    else:
                        logging.log(logging.INFO, f'Command executed successfully. {player_data}')
                        self.time_executed = time.time()
                        self.last_command = player_data
            else:
                response = self._session.post(player_url, headers=headers, data=json.dumps(player_data))
                if response.status_code != 200:
                    try:
                        response.json()
                        raise RequestException(f'Command failed: {response.json()}')
                    except json.decoder.JSONDecodeError:
                        raise RequestException(f'Command failed.')
                else:
                    logging.log(logging.INFO, f'Command executed successfully. {player_data}')
                    self.time_executed = time.time()
                    self.last_command = player_data
        time.sleep(0.5)
