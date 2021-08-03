from experimental import SpotifyPlayer
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)-8s - %(name)-14s - %(message)s')

spotifyplayer = SpotifyPlayer()
spotifyplayer.command(spotifyplayer.play('5wilF6g0r4VpNqQsV8fWKr'))

spotifyplayer.disconnect()
