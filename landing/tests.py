"""Automated checks for the main workflow and the hostel-based access rules.
Run with:  python manage.py test
"""
from django.test import TestCase
from django.urls import reverse

from .models import Complaint, ComplaintCategory, ComplaintUpdate, CustomUser, Hostel, assign_room

R = CustomUser.Role
PW = "Str0ng-Pass-2026"


def make_user(email, role, hostel=None, approved=True, **kw):
    user = CustomUser.objects.create_user(email=email, password=PW, role=role, hostel=hostel,
                                          is_approved=approved, first_name=kw.pop("first", "Test"), last_name="User", **kw)
    if role == R.STUDENT and hostel:
        user.room = assign_room(hostel)
        user.save()
    return user


class SeedTests(TestCase):
    def test_hostels_and_categories_exist_after_migrate(self):
        self.assertEqual(Hostel.objects.count(), 19)
        self.assertEqual(Hostel.objects.filter(gender_type="MALE").count(), 3)
        self.assertEqual(Hostel.objects.filter(gender_type="FEMALE").count(), 14)
        self.assertEqual(Hostel.objects.filter(gender_type="POSTGRAD").count(), 2)
        self.assertEqual(
            set(ComplaintCategory.objects.values_list("name", flat=True)),
            {"Theft", "Facility Issue", "Sexual Abuse", "Bullying", "Cult-related Issue"},
        )


class WorkflowTests(TestCase):
    def setUp(self):
        self.hostel_a = Hostel.objects.get(name="Awolowo Hall")
        self.hostel_b = Hostel.objects.get(name="Mbanefo Hostel")
        self.student_a = make_user("sa@x.test", R.STUDENT, self.hostel_a)
        self.student_b = make_user("sb@x.test", R.STUDENT, self.hostel_b)
        self.warden_a = make_user("wa@x.test", R.WARDEN, self.hostel_a)
        self.warden_b = make_user("wb@x.test", R.WARDEN, self.hostel_b)
        self.staff = make_user("st@x.test", R.STAFF)
        self.admin = make_user("ad@x.test", R.ADMIN)
        self.facility = ComplaintCategory.objects.get(name="Facility Issue")
        self.theft = ComplaintCategory.objects.get(name="Theft")

    def login(self, user):
        self.client.logout()
        self.assertTrue(self.client.login(username=user.email, password=PW))

    def submit(self, category=None):
        self.login(self.student_a)
        resp = self.client.post(reverse("landing:submit-complaint"), {
            "title": "No water", "category": (category or self.facility).pk,
            "priority": "HIGH", "description": "There has been no water since Monday.",
        })
        self.assertEqual(resp.status_code, 302)
        return Complaint.objects.latest("id")

    # ---- submission stores the right data
    def test_student_submits_complaint(self):
        c = self.submit()
        self.assertEqual((c.student, c.hostel, c.status), (self.student_a, self.hostel_a, "PENDING"))
        self.assertEqual(c.room, self.student_a.room)
        self.assertEqual(c.updates.count(), 1)

    # ---- hostel scope
    def test_warden_sees_only_own_hostel(self):
        c = self.submit()
        self.login(self.warden_a)
        self.assertContains(self.client.get(reverse("landing:warden-dashboard")), "No water")
        self.assertEqual(self.client.get(reverse("landing:manage-complaint", args=[c.pk])).status_code, 200)
        self.login(self.warden_b)
        self.assertNotContains(self.client.get(reverse("landing:warden-dashboard")), "No water")
        self.assertEqual(self.client.get(reverse("landing:manage-complaint", args=[c.pk])).status_code, 404)
        resp = self.client.post(reverse("landing:manage-complaint", args=[c.pk]),
                                {"action": "update", "status": "IN_PROGRESS", "message": "hacking"})
        self.assertEqual(resp.status_code, 404)

    def test_student_cannot_open_others_complaint(self):
        c = self.submit()
        self.login(self.student_b)
        self.assertEqual(self.client.get(reverse("landing:view-complaint", args=[c.pk])).status_code, 404)

    def test_admin_sees_everything_and_filters(self):
        c = self.submit()
        self.login(self.admin)
        self.assertContains(self.client.get(reverse("landing:admin-dashboard")), "No water")
        url = reverse("landing:admin-dashboard") + f"?hostel={self.hostel_b.pk}"
        self.assertNotContains(self.client.get(url), "No water")
        self.assertEqual(self.client.get(reverse("landing:admin-complaint", args=[c.pk])).status_code, 200)

    # ---- roles cannot cross over
    def test_role_barriers(self):
        self.login(self.student_a)
        for name in ["warden-dashboard", "staff-dashboard", "admin-dashboard", "manage-users"]:
            self.assertEqual(self.client.get(reverse(f"landing:{name}")).status_code, 403, name)
        self.login(self.warden_a)
        self.assertEqual(self.client.get(reverse("landing:admin-dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("landing:submit-complaint")).status_code, 403)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        resp = self.client.get(reverse("landing:student-dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    # ---- history is preserved
    def test_status_flow_and_history(self):
        c = self.submit()
        self.login(self.warden_a)
        url = reverse("landing:manage-complaint", args=[c.pk])
        self.client.post(url, {"action": "assign", "technician": self.staff.pk})
        c.refresh_from_db()
        self.assertEqual(c.assigned_to, self.staff)
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("landing:view-complaint-staff", args=[c.pk])).status_code, 200)
        self.client.post(reverse("landing:update-complaint-status", args=[c.pk]),
                         {"status": "IN_PROGRESS", "message": "Repair started."})
        self.client.post(reverse("landing:update-complaint-status", args=[c.pk]),
                         {"status": "RESOLVED", "message": "Pipe fixed."})
        c.refresh_from_db()
        self.assertEqual(c.status, "RESOLVED")
        self.assertIsNotNone(c.resolved_at)
        history = list(c.updates.values_list("status_changed_to", flat=True))
        self.assertEqual(history, ["PENDING", "PENDING", "IN_PROGRESS", "RESOLVED"])
        # cannot move backwards
        self.client.post(reverse("landing:update-complaint-status", args=[c.pk]),
                         {"status": "PENDING", "message": "reopen"})
        c.refresh_from_db()
        self.assertEqual(c.status, "RESOLVED")
        # student sees history and rates once
        self.login(self.student_a)
        self.assertContains(self.client.get(reverse("landing:view-complaint", args=[c.pk])), "Pipe fixed.")
        self.client.post(reverse("landing:rate-complaint", args=[c.pk]), {"rating": "5", "feedback": "Great"})
        c.refresh_from_db()
        self.assertEqual(c.student_rating, 5)

    def test_staff_sees_only_assigned(self):
        c = self.submit()
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("landing:view-complaint-staff", args=[c.pk])).status_code, 404)

    def test_sensitive_categories_not_assignable(self):
        c = self.submit(self.theft)
        self.login(self.warden_a)
        self.client.post(reverse("landing:manage-complaint", args=[c.pk]), {"action": "assign", "technician": self.staff.pk})
        c.refresh_from_db()
        self.assertIsNone(c.assigned_to)

    # ---- every page renders
    def test_pages_render(self):
        c = self.submit()
        public = ["home", "login", "register"]
        for name in public:
            self.client.logout()
            self.assertEqual(self.client.get(reverse(f"landing:{name}")).status_code, 200, name)
        pages = {
            self.student_a: [("student-dashboard", []), ("submit-complaint", []), ("view-complaint", [c.pk]), ("profile", [])],
            self.warden_a: [("warden-dashboard", []), ("manage-complaint", [c.pk]), ("profile", [])],
            self.admin: [("admin-dashboard", []), ("admin-complaint", [c.pk]), ("manage-users", []), ("admin-user-add", []),
                         ("manage-hostels", []), ("hostel-add", []), ("manage-categories", []), ("category-add", []),
                         ("admin-user-edit", [self.warden_a.pk]), ("hostel-edit", [self.hostel_a.pk]),
                         ("category-edit", [self.facility.pk]), ("profile", [])],
        }
        for user, items in pages.items():
            self.login(user)
            for name, args in items:
                self.assertEqual(self.client.get(reverse(f"landing:{name}", args=args)).status_code, 200, name)
        self.login(self.student_a)
        c.status = "RESOLVED"
        c.save()
        self.assertEqual(self.client.get(reverse("landing:rate-complaint", args=[c.pk])).status_code, 200)
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("landing:staff-dashboard")).status_code, 200)

    def test_404_page(self):
        self.assertEqual(self.client.get("/does-not-exist/").status_code, 404)


class RegistrationTests(TestCase):
    def data(self, **extra):
        base = {"email": "New@Student.test", "password1": PW, "password2": PW, "first_name": "New", "last_name": "Student",
                "phone": "", "role": "STUDENT", "hostel_id": Hostel.objects.get(name="Bello Hall").pk}
        base.update(extra)
        return base

    def test_student_registration_assigns_hostel_and_room(self):
        resp = self.client.post(reverse("landing:register"), self.data())
        self.assertRedirects(resp, reverse("landing:dashboard"), fetch_redirect_response=False)
        u = CustomUser.objects.get(email="new@student.test")
        self.assertEqual(u.hostel.name, "Bello Hall")
        self.assertEqual(u.room.hostel, u.hostel)
        self.assertTrue(u.check_password(PW))
        self.assertNotEqual(u.password, PW)

    def test_student_needs_hostel(self):
        resp = self.client.post(reverse("landing:register"), self.data(hostel_id=""))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(email="new@student.test").exists())

    def test_warden_waits_for_approval(self):
        self.client.post(reverse("landing:register"), self.data(email="w@w.test", role="WARDEN"))
        u = CustomUser.objects.get(email="w@w.test")
        self.assertFalse(u.is_approved)
        resp = self.client.post(reverse("landing:login"), {"email": "w@w.test", "password": PW})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_cannot_self_register_as_admin(self):
        self.client.post(reverse("landing:register"), self.data(email="a@a.test", role="ADMIN"))
        self.assertFalse(CustomUser.objects.filter(email="a@a.test").exists())

    def test_login_is_case_insensitive_and_wrong_password_fails(self):
        make_user("case@x.test", R.STUDENT, Hostel.objects.first())
        bad = self.client.post(reverse("landing:login"), {"email": "case@x.test", "password": "nope"})
        self.assertEqual(bad.status_code, 200)
        ok = self.client.post(reverse("landing:login"), {"email": "CASE@x.test", "password": PW})
        self.assertEqual(ok.status_code, 302)


class AdminManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user("ad@x.test", R.ADMIN)
        self.client.login(username="ad@x.test", password=PW)

    def test_admin_approves_warden(self):
        w = make_user("w@x.test", R.WARDEN, Hostel.objects.first(), approved=False)
        self.client.post(reverse("landing:admin-user-action", args=[w.pk]), {"action": "approve"})
        w.refresh_from_db()
        self.assertTrue(w.is_approved)

    def test_admin_creates_hostel_and_warden(self):
        self.client.post(reverse("landing:hostel-add"), {"name": "Test Hall", "gender_type": "MALE", "is_active": "on"})
        h = Hostel.objects.get(name="Test Hall")
        self.client.post(reverse("landing:admin-user-add"), {
            "email": "nw@x.test", "first_name": "N", "last_name": "W", "phone": "", "role": "WARDEN",
            "hostel": h.pk, "is_active": "on", "is_approved": "on", "password1": PW, "password2": PW})
        self.assertEqual(CustomUser.objects.get(email="nw@x.test").hostel, h)

    def test_admin_cannot_deactivate_self(self):
        self.client.post(reverse("landing:admin-user-action", args=[self.admin.pk]), {"action": "deactivate"})
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
