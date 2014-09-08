TIMESEEKRANGE_DLNA_ORG = 'TimeSeekRange.dlna.org'
CONTENTFEATURES_DLNA_ORG = 'contentFeatures.dlna.org'
TRANSFERMODE_DLNA_ORG = 'transferMode.dlna.org'

# flags are in hex. trailing 24 zeroes, 26 are after the space
# "DLNA.ORG_OP=" time-seek-range-supp bytes-range-header-supp
#CONTENT_FEATURES = 'DLNA.ORG_OP=10;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=017000 00000000000000000000000000000000'

class DLNAContentFeatures:

    def __init__(self, **initial):
        self.support_time_seek = False
        self.support_range = False
        self.transcoded = False
        self.__dict__.update(initial)

    def __str__(self):
        return 'DLNA.ORG_OP={}{};DLNA.ORG_CI={};DLNA.ORG_FLAGS=017000 00000000000000000000000000000000'.format(
            ('1' if self.support_time_seek else '0'),
            ('1' if self.support_range else '0'),
            ('1' if self.transcoded else '0'),)

