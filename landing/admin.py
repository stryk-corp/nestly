"""Django admin site registrations (database-level management)."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Complaint, ComplaintCategory, ComplaintUpdate, CustomUser, Hostel, Room


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "role", "hostel", "is_approved", "is_active")
    list_filter = ("role", "is_approved", "is_active", "hostel")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone")}),
        ("Nestly", {"fields": ("role", "hostel", "room", "is_approved")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "username", "role", "hostel", "password1", "password2")}),
    )


@admin.register(Hostel)
class HostelAdmin(admin.ModelAdmin):
    list_display = ("name", "gender_type", "is_active")
    list_filter = ("gender_type", "is_active")
    search_fields = ("name",)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("room_number", "hostel", "capacity")
    list_filter = ("hostel",)


@admin.register(ComplaintCategory)
class ComplaintCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "allows_technician", "is_active")


class ComplaintUpdateInline(admin.TabularInline):
    model = ComplaintUpdate
    extra = 0
    readonly_fields = ("updated_by", "message", "status_changed_to", "created_at")
    can_delete = False  # history is never deleted


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "student", "hostel", "category", "status", "priority", "created_at")
    list_filter = ("status", "priority", "category", "hostel")
    search_fields = ("title", "student__email")
    inlines = [ComplaintUpdateInline]
