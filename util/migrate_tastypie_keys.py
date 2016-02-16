#!/usr/bin/env python

"""
Script that migrates TastyPie API keys to Django REST Framework tokens. Makes the Token
the same as the API key which removes the burden for client to configure a new value in
their application(s) writing to esmond.
"""

import django
from django.contrib.auth.models import User
from tastypie.models import ApiKey
from rest_framework.authtoken.models import Token

django.setup()
for tp_user in User.objects.all():
    try:
        tp_key = ApiKey.objects.get(user=tp_user)
        token = Token.objects.get(user=tp_user)
        print 'Key   {0} exists for user {1}'.format(tp_key, tp_user)
        print 'Token {0} exists for user {1}'.format(token, tp_user)
        if(token.key != tp_key.key):
            token.delete() #delete the old token so we can update primary key
            token.key = tp_key.key #make it match old key
            token.save() #create a new token
        tp_key.delete() #delete the old api key
    except ApiKey.DoesNotExist:
        print 'User {0} does not have an old api key - skipping'.format(tp_user)
    except Token.DoesNotExist:
        token = Token.objects.create(user=tp_user, key=tp_key.key)
        tp_key.delete()
        print 'Token {0} created for user {1}'.format(token, tp_user)