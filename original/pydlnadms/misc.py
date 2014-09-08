import mimetypes

def guess_mimetype(path):
    type = mimetypes.guess_type(path)[0]
    if type is None:
        type = 'application/octet-stream'
    #if type == 'video/MP2T':
    #    type = 'video/mpeg'
    return type
    #return 'video/x-msvideo'
    #return 'video/MP2T'
