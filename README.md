# spotify-free-api-player
This allows you to modify the user's playback state through the spotify API, without needing premium.

# Prerequisites
You must have logged in once to open.spotify.com through Microsoft Edge (can change browser, see `examples.py`).

# How it works:
This program checks for the local cookies for open.spotify.com and other related domains for Microsoft Edge. These cookies contain information that are used to login to Spotify, without needing to reenter credentials. This program generates a access token with these cookies to the url `https://open.spotify.com/get_access_token?reason=transport&productType=web_player` with a GET request, and uses that access token to open a websocket connection to `wss://guc3-dealer.spotify.com/?access_token={access_token}`. This websocket connection then recieves information about its Spotify connection ID, which we can then use to create a fake device through the POST request to `https://guc-spclient.spotify.com/track-playback/v1/devices`. After that, we register notifications to recieve events about the queue through the put requests `https://api.spotify.com/v1/me/notifications/user?connection_id={connection_id}` and `https://guc-spclient.spotify.com/connect-state/v1/devices/hobs_{device_id}`.This device is capable of sending requests to play to the user's main device, like the app, through the POST request to `https://guc-spclient.spotify.com/connect-state/v1/player/command/from/{fake_device_id}/to/{playback_device_id}`.

# Known issues:
If the user isn't playing any tracks, a non 200 response code will be returned upon trying to send a request to modify the user's playback.
Possible fix: Create another fake device with the right cookies using selenium, and send the playback commands to that "device".

# Other:
This project woudn't be possible without the Chrome Dev Console, and the npm package sactivity.
This is also still in development.
