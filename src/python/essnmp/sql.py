from sqlalchemy import *
from essnmp.thrift.ttypes import *

db = create_engine("postgres:///essnmp")
metadata = BoundMetaData(db)

oidtype_table=Table('oidtype', metadata, autoload=True)
mapper(OIDType, oidtype_table)

oid_table = Table('oid', metadata, autoload=True)
mapper(OID, oid_table, properties={'type': relation(OIDType, lazy=False)})

poller_table = Table("poller", metadata, autload=True)
mapper(Poller, poller_table)

oidsetmember_table = Table('oidsetmember', metadata, autoload=True)

oidset_table = Table('oidset', metadata, autoload=True)
mapper(OIDSet, oidset_table, properties = {
    'oids': relation(OID, secondary=oidsetmember_table, lazy=False),
    'poller': relation(Poller, lazy=False) })

devicetag_table = Table('devicetag', metadata, autoload=True)
mapper(DeviceTag, devicetag_table)

deviceoidsetmap_table = Table('deviceoidsetmap', metadata, autoload=True)
devicetagmap_table = Table('devicetagmap', metadata, autoload=True)

device_table = Table('device', metadata, autoload=True)
mapper(Device, device_table, \
        properties={
            'oidsets': relation(OIDSet, secondary=deviceoidsetmap_table, lazy=False), 
            'tags': relation(DeviceTag, secondary=devicetagmap_table, lazy=False), 
        })

ifref_table = Table('ifref', metadata, autoload=True)
mapper(IfRef, ifref_table, properties={'device': relation(Device, lazy=False)})
