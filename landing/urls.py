"""URL routes for the Nestly app. Custom admin pages live under control/ so they never clash with Django's admin/."""
from django.urls import path

from . import views

app_name = "landing"

urlpatterns = [
    # Public
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.user_logout, name="logout"),

    # Signed-in (all roles)
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),

    # Student
    path("student/dashboard/", views.student_dashboard, name="student-dashboard"),
    path("student/submit-complaint/", views.submit_complaint, name="submit-complaint"),
    path("student/complaint/<int:pk>/", views.view_complaint, name="view-complaint"),
    path("student/complaint/<int:pk>/rate/", views.rate_complaint, name="rate-complaint"),

    # Warden
    path("warden/dashboard/", views.warden_dashboard, name="warden-dashboard"),
    path("warden/complaint/<int:pk>/", views.manage_complaint, name="manage-complaint"),

    # Maintenance staff
    path("staff/dashboard/", views.staff_dashboard, name="staff-dashboard"),
    path("staff/complaint/<int:pk>/", views.view_complaint_staff, name="view-complaint-staff"),
    path("staff/complaint/<int:pk>/update/", views.update_complaint_status, name="update-complaint-status"),

    # Administrator
    path("control/dashboard/", views.admin_dashboard, name="admin-dashboard"),
    path("control/complaint/<int:pk>/", views.admin_complaint, name="admin-complaint"),
    path("control/users/", views.manage_users, name="manage-users"),
    path("control/users/add/", views.admin_user_form, name="admin-user-add"),
    path("control/users/<int:pk>/edit/", views.admin_user_form, name="admin-user-edit"),
    path("control/users/<int:pk>/action/", views.admin_user_action, name="admin-user-action"),
    path("control/hostels/", views.manage_hostels, name="manage-hostels"),
    path("control/hostels/add/", views.hostel_form, name="hostel-add"),
    path("control/hostels/<int:pk>/edit/", views.hostel_form, name="hostel-edit"),
    path("control/hostels/<int:pk>/toggle/", views.hostel_toggle, name="hostel-toggle"),
    path("control/categories/", views.manage_categories, name="manage-categories"),
    path("control/categories/add/", views.category_form, name="category-add"),
    path("control/categories/<int:pk>/edit/", views.category_form, name="category-edit"),
    path("control/categories/<int:pk>/toggle/", views.category_toggle, name="category-toggle"),
]
