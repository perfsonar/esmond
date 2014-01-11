import datetime
import json
import os

from django.conf import settings
from django.contrib.auth.models import User, Group, Permission
from django.utils.timezone import utc, make_aware, now

from tastypie.models import ApiKey

from esmond.api.models import *
from esmond.util import max_datetime

class TestData(object):
    pass

def load_test_data(name):
    # Path for development mode/env from mkdevenv
    path = os.path.join(settings.ESMOND_ROOT, "..", "test_data", name)
    if not os.path.exists(path):
        # If not, reset to esmond root
        path = os.path.join(settings.ESMOND_ROOT, "test_data", name)

    d = json.loads(open(path).read())
    return d

def build_default_metadata():
    """Builds default data for testing

    The following devices are created:

    rtr_a -- basic, currently active router
    rtr_b -- basic, currently inactive router

    rtr_alu -- ALUFastPollHC and ALUErrors, currently active router
    rtr_inf -- InfineraFastPollHC, currently active router

    The following users are created with API keys:

    user_admin  -- has full admin rights
    user_seeall -- has ability to see hidden interfaces

    """
    td = TestData()
    
    td.rtr_a, _ = Device.objects.get_or_create(
            name="rtr_a",
            community="public",
            begin_time=now())

    DeviceOIDSetMap(device=td.rtr_a,
            oid_set=OIDSet.objects.get(name="FastPollHC")).save()
    DeviceOIDSetMap(device=td.rtr_a,
            oid_set=OIDSet.objects.get(name="Errors")).save()
    DeviceOIDSetMap(device=td.rtr_a,
            oid_set=OIDSet.objects.get(name="IfRefPoll")).save()

    rtr_b_begin = make_aware(datetime.datetime(2013,6,1), utc)
    rtr_b_end = make_aware(datetime.datetime(2013,6,15), utc)
    td.rtr_b, _ = Device.objects.get_or_create(
            name="rtr_b",
            community="public",
            begin_time = rtr_b_begin,
            end_time = rtr_b_end)

    DeviceOIDSetMap(device=td.rtr_b,
            oid_set=OIDSet.objects.get(name="FastPollHC")).save()

    td.rtr_inf, _ = Device.objects.get_or_create(
            name="rtr_inf",
            community="public",
            begin_time=now())

    DeviceOIDSetMap(device=td.rtr_inf,
            oid_set=OIDSet.objects.get(name="InfFastPollHC")).save()

    td.rtr_alu, _ = Device.objects.get_or_create(
            name="rtr_alu",
            community="public",
            begin_time=now())

    DeviceOIDSetMap(device=td.rtr_alu,
            oid_set=OIDSet.objects.get(name="ALUFastPollHC")).save()
    DeviceOIDSetMap(device=td.rtr_alu,
            oid_set=OIDSet.objects.get(name="ALUErrors")).save()

    td.rtr_z_post_data = {
        "name": "rtr_z",
        "community": "private",
    }

    IfRef.objects.get_or_create(
            device=td.rtr_a,
            begin_time=td.rtr_a.begin_time,
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
            device=td.rtr_a,
            begin_time=td.rtr_a.begin_time,
            ifIndex=1,
            ifDescr="xe-1/0/0",
            ifAlias="test interface:hide:",
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
            end_time=rtr_b_begin + datetime.timedelta(days=4))

    IfRef.objects.get_or_create(
            device=td.rtr_b,
            ifIndex=1,
            ifDescr="xe-2/0/0",
            ifAlias="test interface with new ifAlias",
            ipAddr="10.0.1.2",
            ifSpeed=0,
            ifHighSpeed=10000,
            ifMtu=9000,
            ifOperStatus=1,
            ifAdminStatus=1,
            ifPhysAddress="00:00:00:00:00:00",
            begin_time=rtr_b_begin + datetime.timedelta(days=4),
            end_time=rtr_b_begin + datetime.timedelta(days=7))

    IfRef.objects.get_or_create(
            device=td.rtr_inf,
            begin_time=td.rtr_inf.begin_time,
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

    IfRef.objects.get_or_create(
            device=td.rtr_alu,
            begin_time=td.rtr_inf.begin_time,
            ifIndex=1,
            ifDescr="3/1/1",
            ifAlias="test interface",
            ipAddr="10.0.0.4",
            ifSpeed=0,
            ifHighSpeed=10000,
            ifMtu=9000,
            ifOperStatus=1,
            ifAdminStatus=1,
            ifPhysAddress="00:00:00:00:00:00")

    users_testdata(td)

    return td

def users_testdata(td):

    seeall = Permission.objects.get(codename="can_see_hidden_ifref")

    td.user_admin = User(username="admin", is_staff=True)
    td.user_admin.save()
    td.user_admin.user_permissions.add(seeall)

    for resource in ['timeseries']:
        for perm_name in ['view', 'add', 'change', 'delete']:
            perm = Permission.objects.get(
                    codename="esmond_api.{0}_{1}".format(perm_name, resource))
            td.user_admin.user_permissions.add(perm)

    td.user_admin.save()
    td.user_admin_apikey = ApiKey(user=td.user_admin)
    td.user_admin_apikey.key = td.user_admin_apikey.generate_key()
    td.user_admin_apikey.save()
    td.user_admin.save()

    td.user_seeall = User(username="seeall", is_staff=False)
    td.user_seeall.save()
    td.user_seeall.user_permissions.add(seeall)
    td.user_seeall.save()
    td.user_seeall_apikey = ApiKey(user=td.user_seeall)
    td.user_seeall_apikey.key = td.user_seeall_apikey.generate_key()
    td.user_seeall_apikey.save()

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
            begin_time=make_aware(datetime.datetime(2011,11,14), utc),
            end_time=max_datetime)

    users_testdata(td)

    return td

def build_metadata_from_test_data(data):
    """Inserts OIDSetMap entries and IfRef data to allow API access to test data.

    Assumes that all entries in the example data have the same set of interfaces
    and the same OIDSet."""

    d = data[0]

    device = Device.objects.get(name=d['device_name'])
    DeviceOIDSetMap(device=device,
            oid_set=OIDSet.objects.get(name=d['oidset_name'])).save()

    ifnames = set([ x[0][-1] for x in d['data'] ])
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

def build_pdu_metadata():
    td = TestData()

    td.pdu_a, _ = Device.objects.get_or_create(
            name="sentry_pdu",
            community="public",
            begin_time=now())

    DeviceOIDSetMap(device=td.pdu_a,
            oid_set=OIDSet.objects.get(name="SentryOutletRefPoll")).save()
    DeviceOIDSetMap(device=td.pdu_a,
            oid_set=OIDSet.objects.get(name="SentryPoll")).save()

    OutletRef.objects.get_or_create(
        device=td.pdu_a,
        begin_time=td.pdu_a.begin_time,
        outletID="AA",
        outletName="rtr_a:PEM1:50A",
        outletStatus=1,
        outletControlState=1
    )

    return td