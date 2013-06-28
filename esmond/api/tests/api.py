import json

from django.core.urlresolvers import reverse
from django.test import TestCase

from esmond.api.models import *

class DeviceAPITests(TestCase):
    def setUp(self):
        rtr_a = Device.objects.get_or_create(
                name="rtr_a", 
                community="public")

    def test_list(self):
        url = '/v1/device/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEquals(len(data), 1)

