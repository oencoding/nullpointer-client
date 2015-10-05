'''
Represents an item to be displayed by the viewer. Consists 
of a media type, the URI to the content and the time the media should 
be displayed
'''

class Media(object):
    VIDEO = 'video'
    IMAGE = 'image'
    WEB_PAGE = 'web_page'
    
    def __init__(self, content_type, content_uri, view_time):
         self.content_type = content_type
         self.content_uri = content_uri
         self.view_time = view_time
