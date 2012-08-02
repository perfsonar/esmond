from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.orm import sessionmaker, mapper, relation, MapperExtension, EXT_CONTINUE, scoped_session
from calendar import timegm

vars = {}
tables = {}
Session = None
engine = None
conn = None
metadata = None

class OIDType(object):
    pass

class OID(object):
    pass

class Poller(object):
    pass

class OIDSet(object):
    pass

class Device(object):
    def __init__(self, name, begin_time='NOW', end_time='Infinity',
            community='', active=True):
        self.name = name
        self.begin_time = begin_time
        self.end_time = end_time
        self.community = community
        self.active = active

class DeviceTag(object):
    pass

class IfRef(object):
    pass

class LSPOpStatus(object):
    pass

class ALUSAPRef(object):
    pass

def setup_db(db_uri):
    global engine, conn, metadata, Session

    if engine:
        return

    engine = create_engine(db_uri)
    conn = engine.connect()
    metadata = MetaData(engine)
    Session = scoped_session(sessionmaker(autoflush=True, autocommit=False))

    for table in ( 'oidtype', 'oid', 'poller', 'oidsetmember', 'oidset',
            'device', 'devicetag', 'deviceoidsetmap', 'devicetagmap', 'ifref',
            'lspopstatus', 'alusapref'):

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
                if t > 2**31-1:
                    t = 2**31-1

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

    mapper(LSPOpStatus, tables['lspopstatus'], properties={'device': relation(Device, lazy=False)},
            extension=DateConvMapper())

    mapper(ALUSAPRef, tables['alusapref'], properties={'device': relation(Device, lazy=False)},
            extension=DateConvMapper())

    mapper(IfRef, tables['ifref'], properties={'device': relation(Device, lazy=False)},
            extension=DateConvMapper())

def get_devices(active=True, polling_tag=None):
    d = {}
    session = Session()

    if polling_tag:
        extra = """
            AND device.id IN
                (SELECT deviceid
                    FROM devicetagmap
                   WHERE devicetagid =
                   (SELECT devicetag.id
                      FROM devicetag
                     WHERE name = '%s'))
        """ % self.config.polling_tag
    else:
        extra = ''

    devices = session.query(Device).filter("""
            active = '%s' 
            AND end_time > 'NOW'""" % (str(active),) + extra)

    for device in devices:
        d[device.name] = device

    session.close()

    return d
