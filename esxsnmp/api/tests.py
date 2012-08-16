"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

import json
import datetime

from collections import namedtuple

from django.test import TestCase

from esxsnmp.api.models import Device, IfRef, ALUSAPRef

from esxsnmp.persist import IfRefPollPersister, ALUSAPRefPersister, PersistQueueEmpty

ifref_test_data = """
[{
    "oidset_name": "IfRefPoll", 
    "device_name": "router_a", 
    "timestamp": 1345125600,
    "oid_name": "", 
    "data": {
        "ifSpeed": [ [ "ifSpeed.1", 1000000000 ] ], 
        "ifType": [ [ "ifType.1", 53 ] ], 
        "ipAdEntIfIndex": [ [ "ipAdEntIfIndex.10.37.37.1", 1 ] ], 
        "ifHighSpeed": [ [ "ifHighSpeed.1", 1000 ] ], 
        "ifAlias": [ [ "ifAlias.1", "test one" ] ], 
        "ifPhysAddress": [ [ "ifPhysAddress.1", "\u0000\u001c\u000fFk@" ] ], 
        "ifAdminStatus": [ [ "ifAdminStatus.1", 1 ] ], 
        "ifDescr": [ [ "ifDescr.1", "Vlan1" ] ], 
        "ifMtu": [ [ "ifMtu.1", 1500 ] ], 
        "ifOperStatus": [ [ "ifOperStatus.1", 1 ] ]
    }
},
{
    "oidset_name": "IfRefPoll", 
    "device_name": "router_a", 
    "timestamp": 1345125660,
    "oid_name": "", 
    "data": {
        "ifSpeed": [ [ "ifSpeed.1", 1000000000 ] ], 
        "ifType": [ [ "ifType.1", 53 ] ], 
        "ipAdEntIfIndex": [ [ "ipAdEntIfIndex.10.37.37.1", 1 ] ], 
        "ifHighSpeed": [ [ "ifHighSpeed.1", 1000 ] ], 
        "ifAlias": [ [ "ifAlias.1", "test two" ] ], 
        "ifPhysAddress": [ [ "ifPhysAddress.1", "\u0000\u001c\u000fFk@" ] ], 
        "ifAdminStatus": [ [ "ifAdminStatus.1", 1 ] ], 
        "ifDescr": [ [ "ifDescr.1", "Vlan1" ] ], 
        "ifMtu": [ [ "ifMtu.1", 1500 ] ], 
        "ifOperStatus": [ [ "ifOperStatus.1", 1 ] ]
    }
}]
"""

empty_ifref_test_data = """
[{
    "oidset_name": "IfRefPoll", 
    "device_name": "router_a", 
    "timestamp": 1345125720,
    "oid_name": "", 
    "data": {
        "ifSpeed": [],
        "ifType": [],
        "ipAdEntIfIndex": [],
        "ifHighSpeed": [],
        "ifAlias": [],
        "ifPhysAddress": [],
        "ifAdminStatus": [],
        "ifDescr": [],
        "ifMtu": [],
        "ifOperStatus": []
    }
}]"""

class TestPollResult(object):
    def __init__(self, d):
        self.__dict__.update(d)

    def __repr__(self):
        s = "TestPollResult("
        for k,v in self.__dict__.iteritems():
            s += "%s: %s, " % (k,v)
        s = s[:-2] + ")"

        return s

class TestPersistQueue(object):
    """Data is a list of dicts, representing the objects"""
    def __init__(self, data):
        self.data = data

    def get(self):
        try:
            return TestPollResult(self.data.pop(0))
        except IndexError:
            raise PersistQueueEmpty()

class SimpleTest(TestCase):
    def test_basic_addition(self):
        """
        Tests that 1 + 1 always equals 2.
        """
        self.assertEqual(1 + 1, 2)

class TestIfRefPersister(TestCase):
    fixtures = ['test_routers.json']

    def test_test(self):
        d = Device.objects.get(name="router_a")
        self.assertEqual(d.name, "router_a")

    def test_persister(self):
        ifrefs = IfRef.objects.filter(device__name="router_a", ifDescr="Vlan1")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 0)

        q = TestPersistQueue(json.loads(ifref_test_data))
        p = IfRefPollPersister([], "test", persistq=q)
        p.run()

        ifrefs = IfRef.objects.filter(device__name="router_a", ifDescr="Vlan1")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 2)

        self.assertEqual(ifrefs[0].ifIndex, ifrefs[1].ifIndex)
        self.assertTrue(ifrefs[0].end_time < datetime.datetime.max)
        self.assertTrue(ifrefs[1].end_time == datetime.datetime.max)
        self.assertTrue(ifrefs[0].ifAlias == "test one")
        self.assertTrue(ifrefs[1].ifAlias == "test two")

        q = TestPersistQueue(json.loads(empty_ifref_test_data))
        p = IfRefPollPersister([], "test", persistq=q)
        p.run()

        ifrefs = IfRef.objects.filter(device__name="router_a", ifDescr="Vlan1")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 2)
       
        self.assertTrue(ifrefs[1].end_time < datetime.datetime.max)

alu_sap_test_data = """
[
    {
        "oidset_name": "ALUSAPRefPoll", 
        "device_name": "router_a", 
        "timestamp": 1345125600, 
        "oid_name": "", 
        "data": {
            "sapDescription": [
                [ "sapDescription.1.1342177281.100", "one" ]
            ], 
            "sapIngressQosPolicyId": [
                [ "sapIngressQosPolicyId.1.1342177281.100", 2 ]
            ], 
            "sapEgressQosPolicyId": [
                [ "sapEgressQosPolicyId.1.1342177281.100", 2 ]
            ]
        }, 
        "metadata": {}
    },
    {
        "oidset_name": "ALUSAPRefPoll", 
        "device_name": "router_a", 
        "timestamp": 1345125660, 
        "oid_name": "", 
        "data": {
            "sapDescription": [
                [ "sapDescription.1.1342177281.100", "two" ]
            ], 
            "sapIngressQosPolicyId": [
                [ "sapIngressQosPolicyId.1.1342177281.100", 2 ]
            ], 
            "sapEgressQosPolicyId": [
                [ "sapEgressQosPolicyId.1.1342177281.100", 2 ]
            ]
        }, 
        "metadata": {}
    }
]
"""
empty_alu_sap_test_data = """
[
    {
        "oidset_name": "ALUSAPRefPoll", 
        "device_name": "router_a", 
        "timestamp": 1345125720, 
        "oid_name": "", 
        "data": {
            "sapDescription": [], 
            "sapIngressQosPolicyId": [], 
            "sapEgressQosPolicyId": []
        }, 
        "metadata": {}
    }
]"""
class TestALUSAPRefPersister(TestCase):
    fixtures = ['test_routers.json']

    def test_persister(self):
        ifrefs = IfRef.objects.filter(device__name="router_a")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 0)

        q = TestPersistQueue(json.loads(alu_sap_test_data))
        p = ALUSAPRefPersister([], "test", persistq=q)
        p.run()

        ifrefs = ALUSAPRef.objects.filter(device__name="router_a", name="1-8_0_0-100")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 2)

        self.assertTrue(ifrefs[0].end_time < datetime.datetime.max)
        self.assertTrue(ifrefs[1].end_time == datetime.datetime.max)
        self.assertTrue(ifrefs[0].sapDescription == "one")
        self.assertTrue(ifrefs[1].sapDescription == "two")

        q = TestPersistQueue(json.loads(empty_alu_sap_test_data))
        p = ALUSAPRefPersister([], "test", persistq=q)
        p.run()

        ifrefs = ALUSAPRef.objects.filter(device__name="router_a", name="1-8_0_0-100")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 2)
       
        self.assertTrue(ifrefs[1].end_time < datetime.datetime.max)
