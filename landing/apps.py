"""App configuration: seeds hostels and complaint categories after every migrate."""
from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_reference_data(sender, **kwargs):
    # Import here so models are ready; runs after migrations finish
    from django.db import DatabaseError

    from .seed import seed_reference_data

    try:
        seed_reference_data(using=kwargs.get("using", "default"))
    except DatabaseError:
        # Tables may not exist yet (e.g. while migrating backwards) - skip quietly
        pass


class LandingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "landing"

    def ready(self):
        # Hostels and categories are always present after `python manage.py migrate`
        post_migrate.connect(_seed_reference_data, sender=self)
