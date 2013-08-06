import datetime
from esmond.api.models import *

class TestData(object):
    pass

def build_default_data():
    td = TestData()
    
    td.rtr_a, _ = Device.objects.get_or_create(
            name="rtr_a",
            community="public")

    DeviceOIDSetMap(device=td.rtr_a,
            oid_set=OIDSet.objects.get(name="FastPollHC")).save()
    DeviceOIDSetMap(device=td.rtr_a,
            oid_set=OIDSet.objects.get(name="Errors")).save()

    rtr_b_begin = datetime.datetime(2013,6,1)
    rtr_b_end = datetime.datetime(2013,6,15)
    td.rtr_b, _ = Device.objects.get_or_create(
            name="rtr_b",
            community="public",
            begin_time = rtr_b_begin,
            end_time = rtr_b_end)

    td.rtr_c, _ = Device.objects.get_or_create(
            name="rtr_c",
            community="public")

    DeviceOIDSetMap(device=td.rtr_c,
            oid_set=OIDSet.objects.get(name="InfFastPollHC")).save()

    td.rtr_z_post_data = {
        "name": "rtr_z",
        "community": "private",
    }

    IfRef.objects.get_or_create(
            device=td.rtr_a,
            ifIndex=1,
            ifDescr="xe-0/0/0",
            ifAlias="test interface",
            ipAddr="10.0.0.1",
            ifSpeed=0,
            ifHighSpeed=10000,
            ifMtu=9000,
            ifOperStatus=1,
            ifAdminStatus=1,
            ifPhysAddress="00:00:00:00:00:00")

    IfRef.objects.get_or_create(
            device=td.rtr_b,
            ifIndex=1,
            ifDescr="xe-1/0/0",
            ifAlias="test interface",
            ipAddr="10.0.0.2",
            ifSpeed=0,
            ifHighSpeed=10000,
            ifMtu=9000,
            ifOperStatus=1,
            ifAdminStatus=1,
            ifPhysAddress="00:00:00:00:00:00",
            begin_time=rtr_b_begin,
            end_time=rtr_b_end)

    IfRef.objects.get_or_create(
            device=td.rtr_b,
            ifIndex=1,
            ifDescr="xe-2/0/0",
            ifAlias="test interface",
            ipAddr="10.0.0.2",
            ifSpeed=0,
            ifHighSpeed=10000,
            ifMtu=9000,
            ifOperStatus=1,
            ifAdminStatus=1,
            ifPhysAddress="00:00:00:00:00:00",
            begin_time=rtr_b_begin,
            end_time=rtr_b_begin + datetime.timedelta(days=7))

    IfRef.objects.get_or_create(
            device=td.rtr_c,
            ifIndex=1,
            ifDescr="xe-3/0/0",
            ifAlias="test interface",
            ipAddr="10.0.0.3",
            ifSpeed=0,
            ifHighSpeed=10000,
            ifMtu=9000,
            ifOperStatus=1,
            ifAdminStatus=1,
            ifPhysAddress="00:00:00:00:00:00")

    return td
