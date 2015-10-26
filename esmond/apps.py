from django.apps import AppConfig

class EsmondAdminConfig(AppConfig):
    """
    This is to differentiate esmond.admin from django.contrib.admin 
    since the app modules need to have unique names.
    """
    name = 'esmond.admin'
    label = 'esmond_admin'