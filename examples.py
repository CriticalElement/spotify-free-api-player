from experimental import SpotifyPlayer
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)-8s - %(name)-14s - %(message)s')

# edge is preferred (and is now default) because reading cookies in chrome > 104.0.5112.102 needs elevation
# https://github.com/borisbabic/browser_cookie3/issues/180
spotifyplayer = SpotifyPlayer(browser='edge')
spotifyplayer.command(spotifyplayer.pause)

spotifyplayer.force_disconnect = True
spotifyplayer.disconnect()
