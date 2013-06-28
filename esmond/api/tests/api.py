import json

from django.core.urlresolvers import reverse
from tastypie.test import ResourceTestCase

from esmond.api.models import *

class DeviceAPITests(ResourceTestCase):
    def setUp(self):
        self.rtr_a, _ = Device.objects.get_or_create(
                name="rtr_a", 
                community="public")

        self.rtr_b_post_data = {
            "name": "rtr_b",
            "community": "private",
        }

        IfRef.objects.get_or_create(
                device=self.rtr_a,
                ifIndex=1,
                ifDescr="xe-1/0/0",
                ifAlias="test interface",
                ipAddr="10.0.0.1",
                ifSpeed=0,
                ifHighSpeed=10000,
                ifMtu=9000,
                ifOperStatus=1,
                ifAdminStatus=1,
                ifPhysAddress="00:00:00:00:00:00")


    def test_get_device_list(self):
        url = '/v1/device/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEquals(len(data), 1)

    def test_post_device_list_unauthenticated(self):
        """We don't allow POSTs at this time.  Once that capability is added
        these tests will need to be expanded."""

        self.assertHttpMethodNotAllowed(
                self.client.post('/v1/device/entries/', format='json',
                    data=self.rtr_b_post_data))

    def test_get_device_interface_list(self):
        url = '/v1/device/rtr_a/interface/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEquals(len(data['objects']), 1)

    def test_get_device_interface_detail(self):
        url = '/v1/device/rtr_a/interface/xe-1_0_0/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEquals(data['ifDescr'], 'xe-1/0/0')

