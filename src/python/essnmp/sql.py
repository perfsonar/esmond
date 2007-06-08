from sqlalchemy import *
from essnmp.thrift.ttypes import *

db = create_engine("postgres:///essnmp")
metadata = BoundMetaData(db)

oid_table = Table('oid', metadata, autoload=True)
mapper(OID, oid_table)
oidset_table = Table('oidset', metadata, autoload=True)
oidsetmember_table = Table('oidsetmember', metadata, autoload=True)
mapper(OIDSet, oidset_table, properties = {'oids': relation(OID, secondary=oidsetmember_table, lazy=False)})
device_table = Table('device', metadata, autoload=True)
deviceoidsetmap_table = Table('deviceoidsetmap', metadata, autoload=True)
mapper(Device, device_table, properties={'oidsets': relation(OIDSet, secondary=deviceoidsetmap_table, lazy=False)})
var_table = Table('var', metadata, autoload=True)
mapper(Var, var_table)

