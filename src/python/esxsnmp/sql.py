from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.orm import sessionmaker, mapper, relation, MapperExtension, EXT_CONTINUE
from calendar import timegm

from esxsnmp.rpc.ttypes import *

vars = {}
tables = {}
Session = None
engine = None
conn = None
metadata = None

def setup_db(db_uri):
    global engine, conn, metadata, Session

    engine = create_engine(db_uri)
    conn = engine.connect()
    metadata = MetaData(engine)
    Session = sessionmaker(autoflush=True, transactional=True)

    for table in ( 'oidtype', 'oid', 'poller', 'oidsetmember', 'oidset',
            'device', 'devicetag', 'deviceoidsetmap', 'devicetagmap', 'ifref'):

        tables[table] = Table(table, metadata, autoload=True)

    mapper(OIDType, tables['oidtype'])
    mapper(OID, tables['oid'], properties={'type': relation(OIDType, lazy=False)})
    mapper(Poller, tables['poller'])


    mapper(OIDSet, tables['oidset'],
        properties = {
            'oids': relation(OID, secondary=tables['oidsetmember'], lazy=False),
            'poller': relation(Poller, lazy=False)
        })

    mapper(DeviceTag, tables['devicetag'])

    class DateConvMapper(MapperExtension):
        """
        Converts the datetime.objects into seconds since the epoch
        """
        def convert_time(self, t):
            if type(t) is not int and type(t) is not long:
                t = timegm(t.utctimetuple())
                if t < 0:
                    t = 0
                if t > 2**32-1:
                    t = 2**32-1

            return t

        def append_result(self, mapper, selectcontext, row, instance, result,
                **flags):

            instance.begin_time = self.convert_time(instance.begin_time)
            instance.end_time = self.convert_time(instance.end_time)

            return EXT_CONTINUE

    mapper(Device, tables['device'],
        properties={
            'oidsets': relation(OIDSet, secondary=tables['deviceoidsetmap'], lazy=False), 
            'tags': relation(DeviceTag, secondary=tables['devicetagmap'], lazy=False), 
        }, extension=DateConvMapper())

    mapper(IfRef, tables['ifref'], properties={'device': relation(Device, lazy=False)})

def reconnect():
    global engine, conn
    conn.close()
    conn = engine.connect()
