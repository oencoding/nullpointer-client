import logging
import urllib2
import json
import os
from ast import literal_eval
from display.media import Media

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
        playlist_folder = os.path.dirname(playlist_file);
        if not os.path.exists(playlist_folder):
            os.makedirs(playlist_folder)
        self.PLAYLIST_FILEPATH = playlist_file
        
        # Media folder
        self.MEDIA_FOLDER = config.get('Storage', 'media_folder')
        if not os.path.exists(self.MEDIA_FOLDER):
            os.makedirs(self.MEDIA_FOLDER)
        
        # Create empty playlist
        self.playlist = []

    def fetch_remote_playlist_data(self):
        url = self.PLAYLIST_URL
        self.LOG.debug('Fetching remote playlist from %s' % url)
        try:
            pl_data = urllib2.urlopen(url).read()
            self.LOG.debug('Feteched data: %s' % pl_data)
            return pl_data
        except Exception, e:
            self.LOG.error('Could not fetch playlist %s, %s' % (url, e))
            return None
        
    def fetch_local_playlist_data(self):
        if os.path.isfile(self.PLAYLIST_FILEPATH):
            return open(self.PLAYLIST_FILEPATH).read()
        else:
            self.LOG.debug('No stored playlist')
            return None
            
    def fetch_playlist(self, **kwargs):
        if 'local' in kwargs and kwargs['local'] == True:
            pl_data = self.fetch_local_playlist_data()
        else:
            pl_data = self.fetch_remote_playlist_data()
            with open(self.PLAYLIST_FILEPATH, 'w') as pl_file:
                pl_file.write(pl_data)
            pl_file.close()
        if pl_data is None:
            return self.playlist
        
        # If raw playlist data was acquired, create a playlist
        playlist_dl = json.loads(pl_data)
        self.LOG.debug('Playlist fetched %s', playlist_dl)
        media_schedule = literal_eval(playlist_dl[PlaylistManager.SCHEDULE_NAME_STRING])
        media_schedule = self.generate_viewer_playlist(media_schedule)
        self.LOG.debug('Media schedule %s', media_schedule)
        # if this after playlist saved on disk
        self.download_playlist_files(media_schedule)
        self.playlist = media_schedule
        self.LOG.debug('Using playlist %s', self.playlist)
        return self.playlist

    def generate_viewer_playlist(self, playlist):
        viewer_pl = []
        for content in playlist:
            self.LOG.debug("Generating playlist for content: %s", content)
            content_type = content[PlaylistManager.SCHEDULE_TYPE_STRING]
            content_uri = content[PlaylistManager.SCHEDULE_URI_STRING]
            view_time = int(content[PlaylistManager.SCHEDULE_TIME_STRING])
            m = Media(content_type, content_uri, view_time)
            viewer_pl.append(m)
        return viewer_pl

    # NOTE: Also sets content_uri to local uri
    def download_playlist_files(self, playlist):
        playlist_changed = False
        for content in playlist:
            out_file_path = self.generate_content_filepath(content.content_uri, content.content_type)
            self.LOG.debug(out_file_path)
            if os.path.isfile(out_file_path):
                self.LOG.debug("Found file %s", out_file_path)
                content.content_uri = out_file_path
                continue
            playlist_changed = True
            try:
                self.LOG.debug("Downloading content: %s", content)
                self.download_and_save_content(content.content_uri, out_file_path)
                self.LOG.debug("downloaded_data")
            except Exception, e:
                self.LOG.error('Failed to download content, %s %s', content, e)
                return False
            content.content_uri = out_file_path

        return playlist_changed

    def download_and_save_content(self, content_uri, out_file_path):
        content_uri = self.append_device_id_to_url(content_uri)
        self.LOG.debug("download_content() %s", content_uri)
        response = urllib2.urlopen(content_uri)
        with open(out_file_path, 'wb') as out_file:
            while True:
                chunk = response.read(1024)
                if not chunk:
                    break
                out_file.write(chunk)

    def append_device_id_to_url(self, url):
        device_id_query_param = '?device_id=%s' % self.DEVICE_ID
        return url + device_id_query_param


    def generate_filename(self, content_uri, content_type):
        uri_split = content_uri.split('/')
        if len(uri_split) == 0:
            return str(hash(content_uri)) + '.' + content_type
        else:
            return uri_split[len(uri_split)-1]

    def generate_content_filepath(self, content_uri, content_type):
        file_name = self.generate_filename(content_uri, content_type)
        return self.MEDIA_FOLDER + file_name
        