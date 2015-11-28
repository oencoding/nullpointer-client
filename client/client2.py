from asynch_executor import AsynchExecutor
import logging
import time
from playlist_manager import PlaylistManager
from display.scheduler import Scheduler

class Client(object):

    LOG = logging.getLogger(__name__)

    def __init__(self, config):
        self.executor = AsynchExecutor(2)
        self.pl_manager = PlaylistManager(config)
        self.POLL_TIME = config.getfloat('Client', 'playlist_poll_time')
        self.scheduler = Scheduler()

    def schedule_playlist(self, playlist):
        self.LOG.debug('Client scheduling playlist %s' % playlist)
        if len(playlist) == 0:
            self.LOG.debug('No media to schedule')
            return
        def replace_playlist(scheduled_pl):
            del scheduled_pl[:]
            for media in playlist:
                scheduled_pl.append(media)
        self.scheduler.modify_playlist_atomically(replace_playlist)
        if not self.scheduler.running:
            self.scheduler.start() 
        
    def start(self):
        # Get the first playlist from file. If there is no ready playlist,
        # this returns an empty playlist
        playlist = self.pl_manager.fetch_playlist(local=True)
        self.schedule_playlist(playlist)
        
        # After this, start polling for new playlists asynchronously
        def pl_fetch_success(playlist):
            self.schedule_playlist(playlist)
        def pl_fetch_error(error):
            self.LOG.error('Error fetching playlist: %s' % error)
        self.executor.start()
        try:
            while True:
                if not self.executor.is_full():
                    self.executor.submit(
                        self.pl_manager.fetch_playlist,
                        on_success=pl_fetch_success,
                        on_error=pl_fetch_error
                    )
                else:
                    self.LOG.debug('Executor task queue is full')
                time.sleep(self.POLL_TIME)
        except KeyboardInterrupt:
            self.executor.shutdown()
            if self.scheduler:
                self.scheduler.shutdown()