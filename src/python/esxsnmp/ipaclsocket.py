import socket 
from thrift.transport.TSocket import TSocket, TServerSocket
from esxsnmp.util import get_logger

class IPACLSocket(TServerSocket):
    def _resolveAddr(self):
        return socket.getaddrinfo(self.host, self.port, socket.AF_INET,
                socket.SOCK_STREAM, 0, socket.AI_PASSIVE |
                socket.AI_ADDRCONFIG)

    def __init__(self, port, permit, host='0.0.0.0', log=None, hints={}):
            
        self.permit = permit
        self.host = host
        self.port = port
        self.log = log
        self.hints = {
            'family': socket.AF_UNSPEC,
            'socktype': socket.SOCK_STREAM,
            'proto': 0,
            'flags': socket.AI_PASSIVE}
        self.hints.update(hints)
        TServerSocket.__init__(self, port)

    def listen(self):
        res0 = socket.getaddrinfo(None, self.port, self.hints['family'],
                self.hints['socktype'], self.hints['proto'],
                self.hints['flags'])
        for res in res0:
            if res[0] is socket.AF_INET6 or res is res0[-1]:
                break

        self.handle = socket.socket(res[0], res[1])
        self.handle.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(self.handle, 'set_timeout'):
            self.handle.set_timeout(None)
        self.handle.bind(res[4])
        self.handle.listen(128)

    def accept(self):
        (client, addr) = self.handle.accept()
        if not addr[0].startswith('198.129'):
            if self.log:
                self.log.info('connection rejected from %s' % addr[0])
            client.close()
            return None
        result = TSocket()
        result.setHandle(client)
        return result

