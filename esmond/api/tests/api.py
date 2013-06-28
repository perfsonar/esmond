import json

from django.core.urlresolvers import reverse
from tastypie.test import ResourceTestCase

from esmond.api.models import *

class DeviceAPITests(ResourceTestCase):
    def setUp(self):
        self.rtr_a = Device.objects.get_or_create(
                name="rtr_a", 
                community="public")

        self.rtr_b_post_data = {
            "name": "rtr_b",
            "community": "private",
        }

    def test_list(self):
        url = '/v1/device/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEquals(len(data), 1)

    def test_post_list_unauthenticated(self):
        """We don't allow POSTs at this time.  Once that capability is added
        these tests will need to be expanded."""

        self.assertHttpMethodNotAllowed(
                self.client.post('/v1/device/entries/', format='json',
                    data=self.rtr_b_post_data))


