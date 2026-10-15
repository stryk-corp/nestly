"""Database models for Nestly (users, hostels, rooms, categories, complaints, updates)."""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Count, F


# ================================================================ Hostel
class Hostel(models.Model):
    """A hostel / hall of residence. Hostel is the access-control boundary for wardens."""

    GENDER_CHOICES = [
        ("MALE", "Male"),
        ("FEMALE", "Female"),
        ("POSTGRAD", "Postgraduate & Special"),
    ]

    name = models.CharField(max_length=120, unique=True)
    gender_type = models.CharField(max_length=10, choices=GENDER_CHOICES, default="MALE")
    is_active = models.BooleanField(default=True, help_text="Inactive hostels cannot be chosen at registration.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["gender_type", "name"]

    def __str__(self):
        return self.name


# ================================================================ Room
class Room(models.Model):
    """A room inside a hostel. Students are linked to a room automatically."""

    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name="rooms")
    room_number = models.CharField(max_length=20)
    capacity = models.PositiveSmallIntegerField(default=4)

    class Meta:
        ordering = ["hostel", "room_number"]
        unique_together = [("hostel", "room_number")]

    def __str__(self):
        return f"{self.hostel.name} - {self.room_number}"


def assign_room(hostel):
    """Return a room in `hostel` with free space; create a new room if all are full."""
    with transaction.atomic():
        room = (
            Room.objects.filter(hostel=hostel)
            .annotate(n=Count("residents"))
            .filter(n__lt=F("capacity"))
            .order_by("id")
            .first()
        )
        if room:
            return room
        number = hostel.rooms.count() + 1
        while Room.objects.filter(hostel=hostel, room_number=f"R-{number:03d}").exists():
            number += 1
        return Room.objects.create(hostel=hostel, room_number=f"R-{number:03d}", capacity=4)


# ================================================================ User
class UserManager(BaseUserManager):
    """Manager for an email-based user model."""

    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        extra.setdefault("username", email)
        user = self.model(email=email, **extra)
        user.set_password(password)  # hashes the password
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role="ADMIN", is_approved=True)
        return self._create(email, password, **extra)


class CustomUser(AbstractUser):
    """A Nestly account. Roles: student, warden (hostel porter), maintenance staff, admin."""

    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        WARDEN = "WARDEN", "Hostel warden"
        STAFF = "STAFF", "Maintenance staff"
        ADMIN = "ADMIN", "Administrator"

    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField(max_length=20, blank=True)
    # Students live in a hostel; wardens manage one. Staff are not tied to a hostel.
    hostel = models.ForeignKey(Hostel, null=True, blank=True, on_delete=models.SET_NULL, related_name="members")
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="residents")
    # Wardens and staff must be approved by an administrator before they can sign in
    is_approved = models.BooleanField(default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def save(self, *args, **kwargs):
        # Keep email lowercase and mirror it into the (unused) username column
        self.email = (self.email or "").strip().lower()
        if not self.username:
            self.username = self.email
        if self.is_superuser:
            self.role = self.Role.ADMIN
            self.is_approved = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.email


# ================================================================ Complaint category
class ComplaintCategory(models.Model):
    """Complaint category (Theft, Facility Issue, Sexual Abuse, Bullying, Cult-related Issue)."""

    name = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    # Only categories that need repair work can be assigned to maintenance staff
    allows_technician = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "complaint categories"

    def __str__(self):
        return self.name


# ================================================================ Complaint
class Complaint(models.Model):
    """The central complaint record."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        RESOLVED = "RESOLVED", "Resolved"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    student = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="complaints")
    hostel = models.ForeignKey(Hostel, on_delete=models.PROTECT, related_name="complaints")
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="complaints")
    category = models.ForeignKey(ComplaintCategory, on_delete=models.PROTECT, related_name="complaints")
    title = models.CharField(max_length=120)
    description = models.TextField(max_length=2000)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING, db_index=True)
    image = models.ImageField(upload_to="complaints/%Y/%m/", blank=True, null=True)
    assigned_to = models.ForeignKey(
        CustomUser, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_complaints"
    )
    student_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    student_feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)  # date/time submitted
    updated_at = models.DateTimeField(auto_now=True)      # last updated
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} {self.title}"


# ================================================================ Complaint update (history)
class ComplaintUpdate(models.Model):
    """One timestamped history entry. Rows are only ever added, never edited or removed."""

    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="updates")
    updated_by = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="complaint_updates")
    message = models.TextField(max_length=1000)
    status_changed_to = models.CharField(max_length=15, choices=Complaint.Status.choices)  # status after this update
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"Update on #{self.complaint_id} ({self.status_changed_to})"
