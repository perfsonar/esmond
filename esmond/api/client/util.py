"""Utils for esmond.api.client modules"""

def add_apikey_header(user, key, header_dict):
    header_dict['Authorization'] = 'ApiKey {0}:{1}'.format(user, key)