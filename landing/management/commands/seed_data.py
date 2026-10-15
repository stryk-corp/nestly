"""
python manage.py seed_data          -> make sure all hostels and categories exist
python manage.py seed_data --demo   -> also create demo accounts (development only)
"""
from django.core.management.base import BaseCommand

from landing.models import CustomUser, Hostel, assign_room
from landing.seed import seed_reference_data

DEMO_PASSWORD = "Nestly@2026"


class Command(BaseCommand):
    help = "Seed hostels, complaint categories and (optionally) demo accounts."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true", help="Create demo users for each role.")

    def handle(self, *args, **options):
        # Reference data
        seed_reference_data()
        self.stdout.write(self.style.SUCCESS(f"Hostels in database: {Hostel.objects.count()}"))

        if not options["demo"]:
            return

        # Demo accounts (development only)
        hostel = Hostel.objects.get(name="Awolowo Hall")
        demo = [
            ("admin@nestly.test", "Ada", "Admin", CustomUser.Role.ADMIN, None),
            ("warden@nestly.test", "Wale", "Warden", CustomUser.Role.WARDEN, hostel),
            ("staff@nestly.test", "Sade", "Technician", CustomUser.Role.STAFF, None),
            ("student@nestly.test", "Sola", "Student", CustomUser.Role.STUDENT, hostel),
        ]
        for email, first, last, role, h in demo:
            if CustomUser.objects.filter(email=email).exists():
                continue
            user = CustomUser.objects.create_user(
                email=email, password=DEMO_PASSWORD, first_name=first, last_name=last,
                role=role, hostel=h, is_approved=True,
            )
            if role == CustomUser.Role.STUDENT:
                user.room = assign_room(h)
                user.save(update_fields=["room"])
            self.stdout.write(f"Created {role.lower()}: {email}")
        self.stdout.write(self.style.WARNING(f"Demo password for all demo accounts: {DEMO_PASSWORD}"))
