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


logger = logging.getLogger(__name__)


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

    def __init__(self, event_reciever: typing.List[typing.Callable] = None, cookie_str: str = None,
                 cookie_path: str = None):
        self.isinitialized = False
        if event_reciever is None:
            event_reciever = [lambda: None]
        if cookie_str:
            self.isinitialized = True
        if cookie_path:
            self.isinitialized = True
        self.cookie_path = cookie_path
        self.cookie_str = cookie_str
        if not self.isinitialized:
            try:
                self.cj = browser_cookie3.chrome()
                # noinspection PyProtectedMember
                _ = self.cj._cookies['.spotify.com']['/']['sp_t']
                self.isinitialized = True
            except Exception as e:
                logger.error(e, exc_info=True)
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
        self.force_disconnect = False
        self.active_device_id = ''
        self.current_volume = 65535
        self._last_timestamp = 0
        self._last_position = 0
        self.last_command = None
        self.time_executed = 0
        self.ws = None
        if self.isinitialized:
            self.isinitialized = False
            self._authorize()

    def _authorize(self):
        if self.isinitialized:
            self.isinitialized = False
        access_token_headers = self._default_headers.copy()
        access_token_headers.update({'spotify-app-version': '1.1.48.530.g38509c6c'})
        access_token_url = 'https://open.spotify.com/get_access_token?reason=transport&productType=web_player'
        if self.cookie_path:
            with open(self.cookie_path, 'r') as f:
                self.cookie_str = f.read()
        if self.cookie_str:
            access_token_headers.update({'cookie': self.cookie_str})
            response = self._session.get(access_token_url, headers=access_token_headers)
        else:
            response = self._session.get(access_token_url, headers=access_token_headers, cookies=self.cj)
        access_token_response = response.json()
        self.access_token = access_token_response['accessToken']
        self.access_token_expire = access_token_response['accessTokenExpirationTimestampMs'] / 1000

        guc_url = f'wss://guc3-dealer.spotify.com/?access_token={self.access_token}'
        guc_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'
                                     ' Chrome/87.0.4280.66 Safari/537.36'}

        self.connection_id = None
        self.queue_revision = None

        async def websocket():
            async with websockets.connect(guc_url, extra_headers=guc_headers) as ws:
                self.ws = ws
                while True:
                    try:
                        self.isinitialized = True
                        self.websocket_task_event_loop = asyncio.get_event_loop()
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
                                    try:
                                        update_reason = load['payloads'][0]['update_reason']
                                        if 'DEVICE' in update_reason:
                                            self.devices = load['payloads'][0]['cluster']['devices']
                                    except KeyError:
                                        pass
                                    self.queue_revision = (load['payloads'][0]['cluster']['player_state']
                                                           ['queue_revision'])
                                    options = load['payloads'][0]['cluster']['player_state']['options']
                                    try:
                                        active_device = load['payloads'][0]['cluster']['active_device_id']
                                        self.current_volume = (load['payloads'][0]['cluster']['devices'][active_device]
                                                               ['volume'])
                                        self.active_device_id = active_device
                                    except KeyError:
                                        self.active_device_id = ''
                                    self.playing = not load['payloads'][0]['cluster']['player_state']['is_paused']
                                    self.shuffling = options['shuffling_context']
                                    try:
                                        self._last_timestamp = int(load['payloads'][0]['cluster']['player_state']
                                                                   ['timestamp'])
                                    except KeyError:
                                        self._last_timestamp = 0
                                    position_ms = int(load['payloads'][0]['cluster']['player_state']
                                                      ['position_as_of_timestamp'])
                                    if position_ms != self._last_position:
                                        self._last_position = position_ms
                                    if options['repeating_track']:
                                        self.looping = 'track'
                                    elif options['repeating_context']:
                                        self.looping = 'context'
                                    else:
                                        self.looping = 'off'
                                    [event() for event in self.event_reciever]
                            except AttributeError:
                                pass
                    except websockets.exceptions.ConnectionClosed:
                        return

        async def ping_loop():
            try:
                while True:
                    if self.isinitialized and self.ws:
                        await self.ws.send('{"type": "ping"}')
                        self.sleep_task_event_loop = asyncio.get_event_loop()
                        await asyncio.sleep(5)
                    else:
                        await asyncio.sleep(1)  # don't lag the gui thread
            except asyncio.CancelledError:
                return

        async def run_until_complete():
            self.tasks.append(asyncio.create_task(websocket()))
            self.tasks.append(asyncio.create_task(ping_loop()))
            await asyncio.gather(*self.tasks, return_exceptions=True)

            if not self.force_disconnect:
                self._authorize()

        self.sleep_task_event_loop = None
        self.websocket_task_event_loop = None
        self.tasks = []
        policy = asyncio.get_event_loop_policy()  # workaround to some dumb bug
        policy._loop_factory = asyncio.SelectorEventLoop  # why does this work
        Thread(target=asyncio.run, args=(run_until_complete(),)).start()

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
            logger.info(f'Successfully created Spotify device with id {self.device_id}.')

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
            self.active_device_id = response_load['active_device_id']
            self.devices = response_load['devices']
            self.current_volume = response_load['devices'][self.active_device_id]['volume']
            self.queue_revision = response_load['player_state']['queue_revision']
            self.shuffling = response_options['shuffling_context']
            self.playing = not response_load['player_state']['is_paused']
            self._last_position = int(response_load['player_state']['position_as_of_timestamp'])
            self._last_timestamp = int(response_load['player_state']['timestamp'])
            if response_options['repeating_track']:
                self.looping = 'track'
            elif response_options['repeating_context']:
                self.looping = 'context'
            else:
                self.looping = 'off'
        except KeyError:
            pass

    def get_position(self):
        if not self.playing:
            return self._last_position / 1000
        diff = time.time() - self._last_timestamp / 1000
        return self._last_position / 1000 + diff

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

    def create_api_request(self, path, request_type='GET'):
        if request_type.upper() in ['GET', 'PUT', 'DELETE', 'POST', 'PATCH', 'HEAD']:
            try:
                return getattr(self._session, request_type.lower())('https://api.spotify.com/v1' + path,
                                                                    headers={'Authorization': f'Bearer'
                                                                                              f' {self.access_token}'})
            except RequestException:
                return getattr(self._session, request_type.lower())('https://api.spotify.com/v1' + path,
                                                                    headers={'Authorization': f'Bearer'
                                                                                              f' {self.access_token}'})

    def _cancel_tasks(self):
        print(self.tasks)
        self.websocket_task_event_loop.create_task(self.ws.close())
        [task.cancel() for task in self.tasks]

    def disconnect(self):
        self.force_disconnect = True
        self.websocket_task_event_loop.create_task(self.ws.close())

    def command(self, command_dict):
        if self.access_token_expire < time.time():
            self._authorize()
            while not self.isinitialized:
                pass
        headers = {'Authorization': f'Bearer {self.access_token}'}
        if self.active_device_id:
            currently_playing_device = self.active_device_id
        else:
            currently_playing_device = self._session.get('https://api.spotify.com/v1/me/player',
                                                         headers=headers)
            try:
                currently_playing_device = currently_playing_device.json()['device']['id']
            except json.decoder.JSONDecodeError or KeyError:
                currently_playing_device = self._session.get('https://api.spotify.com/v1/me/player/devices',
                                                             headers=headers).json()['devices'][0]['id']
                self.transfer(currently_playing_device)
                time.sleep(1)
                currently_playing_device = self.active_device_id
            except requests.exceptions.RequestException:
                self._cancel_tasks()
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
                    logger.info(f'Command executed successfully. {player_data}')
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
                        logger.info(f'Command executed successfully. {player_data}')
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
                    logger.info(f'Command executed successfully. {player_data}')
                    self.time_executed = time.time()
                    self.last_command = player_data
        time.sleep(0.5)
