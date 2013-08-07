import datetime
import json
import os

from django.conf import settings
from django.contrib.auth.models import User, Group
from django.utils.timezone import utc, make_aware

from tastypie.models import ApiKey

from esmond.api.models import *
from esmond.util import max_datetime

class TestData(object):
    pass

def load_test_data(name):
    path = os.path.join(settings.ESMOND_ROOT, "..", "test_data", name)
    d = json.loads(open(path).read())
    return d

def build_default_metadata():
    """Builds default data for testing

    The following devices are created:

    rtr_a -- basic, currently active router
    rtr_b -- basic, currently inactive router
    rtr_c -- InfineraFastPollHC, currently active router
    """
    td = TestData()
    
    td.rtr_a, _ = Device.objects.get_or_create(
            name="rtr_a",
            community="public")

    DeviceOIDSetMap(device=td.rtr_a,
            oid_set=OIDSet.objects.get(name="FastPollHC")).save()
    DeviceOIDSetMap(device=td.rtr_a,
            oid_set=OIDSet.objects.get(name="Errors")).save()

    rtr_b_begin = make_aware(datetime.datetime(2013,6,1), utc)
    rtr_b_end = make_aware(datetime.datetime(2013,6,15), utc)
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

def build_rtr_d_metadata():
    """Creates rtr_d, to be used for larger dataset testing

    The following devices are created:

    rtr_d -- FastPollHC, currently active router with IfRefs

    """

    td = TestData()

    td.rtr_d, _ = Device.objects.get_or_create(
            name="rtr_d",
            community= "community_string",
            active=True,
            begin_time="2011-11-14T02:54:14.503",
            end_time=max_datetime)

    return td

def build_metadata_from_test_data(data):
    """Inserts OIDSetMap entries and IfRef data to allow API access to test data.

    Assumes that all entries in the example data have the same set of interfaces
    and the same OIDSet."""

    d = data[0]

    device = Device.objects.get(name=d['device_name'])
    DeviceOIDSetMap(device=device,
            oid_set=OIDSet.objects.get(name=d['oidset_name'])).save()

    ifnames = set([ x[0].split("/")[-1].replace("_","/") for x in d['data'] ])
    t0 = make_aware(datetime.datetime.fromtimestamp(int(d["timestamp"]) - 30),
            utc)
            

    ifIndex = 1

    for ifname in ifnames:
        ifr = IfRef(
                device=device,
                ifIndex=ifIndex,
                ifDescr=ifname,
                ifAlias="test %s" % ifname,
                ipAddr="10.0.0.%d" % ifIndex,
                ifSpeed=0,
                ifHighSpeed=10000,
                ifMtu=9000,
                ifOperStatus=1,
                ifAdminStatus=1,
                ifPhysAddress="00:00:00:00:00:%02d" % ifIndex,
                begin_time=t0,
                end_time=max_datetime)
        ifr.save()

