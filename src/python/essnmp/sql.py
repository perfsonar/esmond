from sqlalchemy import *
from essnmp.rpc.ttypes import *
from calendar import timegm

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

        def append_result(self, mapper, selectcontext, row, instance, identitykey, result, isnew):
            if isnew is not False:
                instance.begin_time = self.convert_time(instance.begin_time)
                instance.end_time = self.convert_time(instance.end_time)

            if result:
                result.append(instance)

            return None

    mapper(Device, tables['device'],
        properties={
            'oidsets': relation(OIDSet, secondary=tables['deviceoidsetmap'], lazy=False), 
            'tags': relation(DeviceTag, secondary=tables['devicetagmap'], lazy=False), 
        }, extension=DateConvMapper())

    mapper(IfRef, tables['ifref'], properties={'device': relation(Device, lazy=False)})
