import logging


class FileResource:

    def __init__(self, path, start=0, end=None):
        self.file = open(path, 'rb')
        self.start = start
        self.end = end
        self.file.seek(start)

    def read(self, count):
        if self.end is not None:
            count = min(self.end - self.file.tell(), count)
        data = self.file.read(count)
        if data:
            return data

    @property
    def size(self):
        import os
        return os.fstat(self.file.fileno()).st_size

    @property
    def length(self):
        if self.end is None:
            return None
        else:
            return self.end - self.start

    def __repr__(self):
        return '<FileResource path=%r, start=%r, end=%r>' % (self.file.name, self.start, self.end)

    def close(self):
        self.file.close()

    def fileno(self):
        return self.file.fileno()
