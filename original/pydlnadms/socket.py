def pretty_sockaddr(addr):
    '''Converts a standard Python sockaddr tuple and returns it in the normal text representation'''
    # IPv4 only?
    assert len(addr) == 2, addr
    return '{}:{:d}'.format(addr[0], addr[1])
