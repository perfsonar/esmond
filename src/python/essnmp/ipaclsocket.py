from thrift.transport.TSocket import TSocket, TServerSocket

class IPACLSocket(TServerSocket):
    def __init__(self, port, permit):
        self.permit = permit
        TServerSocket.__init__(self, port)

    def accept(self):
        (client, addr) = self.handle.accept()
        print client, addr
        result = TSocket()
        result.setHandle(client)
        return result

