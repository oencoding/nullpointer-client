import json
import logging
import os
from ast import literal_eval

import requests

from display.media import Media
from downloader import ChunkedDownloader
from media_cleaner import MediaCleaner


class PlaylistManager(object):

    LOG = logging.getLogger(__name__)
    SCHEDULE_NAME_STRING = 'media_schedule_json'
    SCHEDULE_TIME_STRING = 'time'
    SCHEDULE_TYPE_STRING = 'type'
    SCHEDULE_URI_STRING = 'uri'

    def __init__(self, config):
        # Device ID
        device_id_file = open(config.get('Device', 'device_id_file'), 'r')
        self.DEVICE_ID = device_id_file.read().strip()
        device_id_file.close()

        # Playlist URL
        incomplete_url = config.get('Server', 'playlist_url')
        self.PLAYLIST_URL = incomplete_url.format(**{'device_id': self.DEVICE_ID})

        # Playlist file
        playlist_file = config.get('Storage', 'playlist_file')
        playlist_folder = os.path.dirname(playlist_file)
        if not os.path.exists(playlist_folder):
            os.makedirs(playlist_folder)
        self.PLAYLIST_FILEPATH = playlist_file

        # Media folder
        self.MEDIA_FOLDER = config.get('Storage', 'media_folder')
        if not os.path.exists(self.MEDIA_FOLDER):
            os.makedirs(self.MEDIA_FOLDER)

        # Utility for parsing playlist JSON
        self.PLAYLIST_PARSER = PlaylistJsonParser(
            self.PLAYLIST_FILEPATH
        )

        media_cleaner = MediaCleaner(config, self.PLAYLIST_PARSER)

        # Utility for downloading files
        self.downloader = ChunkedDownloader(self.PLAYLIST_URL,
                                            self.DEVICE_ID,
                                            self.MEDIA_FOLDER,
                                            media_cleaner)

    def fetch_local_playlist(self):
        try:
            local_playlist = self.PLAYLIST_PARSER.get_stored_playlist()
            # We do not download files here because it would defeat the purpose.
            # We trust the files have either been downloaded
            # or we start to download them the next time we download a playlist
            # this way if the playlist has changed we don't unnecessarily download old files
            return local_playlist
        except:
            self.LOG.info('No locally stored playlist')
            return []

    def fetch_remote_playlist_data(self):
        url = self.PLAYLIST_URL
        headers = {
            'Authorization': 'Device %s' % self.DEVICE_ID
        }
        self.LOG.debug('Fetching remote playlist from %s' % url)
        try:
            response = requests.get(
                url,
                timeout=(None, 60),
                stream=False,
                headers=headers)

            if response.status_code == 200:
                self.LOG.debug('Fetched data: %s' % response.content)
                return response.content
            raise Exception('Wrong status from server while fetching playlist: %s', response.status_code)

        except Exception, e:
            self.LOG.error('Could not fetch playlist %s, %s' % (url, e))
            #re-raise error so our async executor knows to not set this as a playlist.
            raise

    def fetch_playlist(self):
        pl_data = self.fetch_remote_playlist_data()
        if pl_data is None:
            raise Exception("No playlist data received from server.")

        playlist = self.parse_playlist(pl_data)
        playlist_files_downloaded = self.download_playlist_files(playlist)
        if playlist_files_downloaded:
            self.PLAYLIST_PARSER.save_playlist_to_file(playlist)
            return playlist
        raise Exception("Files were not downloaded.")

    def parse_playlist(self, pl_data):
        self.LOG.debug("Parsing playlist")
        try:
            playlist_dl = json.loads(pl_data)
        except Exception, e:
            self.LOG.error('Playlist likely corrupted: %s' % e)
            #re-raise error so our async executor knows to not set this as a playlist.
            raise

        self.LOG.debug('Playlist fetched %s', playlist_dl)
        media_schedule = literal_eval(playlist_dl[PlaylistManager.SCHEDULE_NAME_STRING])
        media_schedule = self.generate_viewer_playlist(media_schedule)
        self.LOG.debug('Media schedule %s', media_schedule)
        return media_schedule


    def generate_viewer_playlist(self, playlist):
        viewer_pl = []
        for content in playlist:
            self.LOG.debug("Generating playlist for content: %s", content)
            content_type = content[PlaylistManager.SCHEDULE_TYPE_STRING]
            content_uri = content[PlaylistManager.SCHEDULE_URI_STRING]
            view_time = int(content[PlaylistManager.SCHEDULE_TIME_STRING])
            media = Media(content_type, content_uri, view_time)
            viewer_pl.append(media)
        return viewer_pl

    # NOTE: Also sets content_uri to local uri
    def download_playlist_files(self, playlist):
        for content in playlist:
            if content.content_type == 'web_page':
                continue  # Web pages are not downloaded
            try:
                content.content_uri = self.downloader.download(content)
            except Exception, e:
                self.LOG.error('Failed to download content, %s %s', content, e)
                return False
        return True


class PlaylistJsonParser(object):
    LOG = logging.getLogger(__name__)

    def __init__(self, playlist_filepath):
        self.PLAYLIST_FILEPATH = playlist_filepath

    def parse_playlist_json(self, pl_json):
        playlist = json.loads(pl_json)
        return self.generate_viewer_playlist(playlist)

    def get_stored_playlist(self):
        with open(self.PLAYLIST_FILEPATH, 'r') as pl_file:
            playlist_json = pl_file.read()
        return self.parse_playlist_json(playlist_json)

    def generate_viewer_playlist(self, playlist):
        viewer_pl = []
        for content in playlist:
            content_type = content[PlaylistManager.SCHEDULE_TYPE_STRING]
            content_uri = content[PlaylistManager.SCHEDULE_URI_STRING]
            view_time = int(content[PlaylistManager.SCHEDULE_TIME_STRING])
            media = Media(content_type, content_uri, view_time)
            viewer_pl.append(media)
        return viewer_pl

    def save_playlist_to_file(self, playlist):
        self.LOG.debug('Saving playlist to file')
        json_playlist = []
        for content in playlist:
            json_content = {}
            json_content[PlaylistManager.SCHEDULE_TYPE_STRING] = content.content_type
            json_content[PlaylistManager.SCHEDULE_URI_STRING] = content.content_uri
            json_content[PlaylistManager.SCHEDULE_TIME_STRING] = content.view_time
            json_playlist.append(json_content)
        with open(self.PLAYLIST_FILEPATH, 'w') as pl_file:
            pl_file.write(json.dumps(json_playlist))
        self.LOG.debug("Playlist saved")
