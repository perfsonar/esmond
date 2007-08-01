from sqlalchemy import *
from essnmp.thrift.ttypes import *

vars = {}
tables = {}

def setup_db(db_uri):
    vars['db'] = create_engine(db_uri)
    vars['metadata'] = BoundMetaData(vars['db'])

    for table in ( 'oidtype', 'oid', 'poller', 'oidsetmember', 'oidset',
            'device', 'devicetag', 'deviceoidsetmap', 'devicetagmap', 'ifref'):

        tables[table] = Table(table, vars['metadata'], autoload=True)

    mapper(OIDType, tables['oidtype'])
    mapper(OID, tables['oid'], properties={'type': relation(OIDType, lazy=False)})
    mapper(Poller, tables['poller'])


    mapper(OIDSet, tables['oidset'],
        properties = {
            'oids': relation(OID, secondary=tables['oidsetmember'], lazy=False),
            'poller': relation(Poller, lazy=False)
        })

    mapper(DeviceTag, tables['devicetag'])

    mapper(Device, tables['device'],
        properties={
            'oidsets': relation(OIDSet, secondary=tables['deviceoidsetmap'], lazy=False), 
            'tags': relation(DeviceTag, secondary=tables['devicetagmap'], lazy=False), 
        })

    mapper(IfRef, tables['ifref'], properties={'device': relation(Device, lazy=False)})
