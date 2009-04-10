import socket 
from thrift.transport.TSocket import TSocket, TServerSocket
from esxsnmp.util import get_logger

class IPACLSocket(TServerSocket):
    def _resolveAddr(self):
        return socket.getaddrinfo(self.host, self.port, socket.AF_INET,
                socket.SOCK_STREAM, 0, socket.AI_PASSIVE |
                socket.AI_ADDRCONFIG)
    def __init__(self, port, permit, host='0.0.0.0', log=None):
        self.permit = permit
        self.host = host
        self.port = port
        self.log = log
        TServerSocket.__init__(self, port)

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

