"""Forms with server-side validation for every page that accepts input."""
from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import PasswordChangeForm

from .models import Complaint, ComplaintCategory, CustomUser, Hostel

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB photo limit


# ================================================================ Registration
class RegistrationForm(forms.Form):
    """Account details (step 1 and 2 of the sign-up page). Role and hostel are checked in the view."""

    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={"placeholder": "name@university.edu", "autocomplete": "email"}),
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"placeholder": "At least 8 characters", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"placeholder": "Repeat your password", "autocomplete": "new-password"}),
    )
    first_name = forms.CharField(
        max_length=150, widget=forms.TextInput(attrs={"placeholder": "First name", "autocomplete": "given-name"})
    )
    last_name = forms.CharField(
        max_length=150, widget=forms.TextInput(attrs={"placeholder": "Last name", "autocomplete": "family-name"})
    )
    phone = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. 0803 000 0000", "autocomplete": "tel"}),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "The two passwords do not match.")
            else:
                probe = CustomUser(email=data.get("email", ""), first_name=data.get("first_name", ""),
                                   last_name=data.get("last_name", ""))
                try:
                    password_validation.validate_password(p1, probe)
                except forms.ValidationError as exc:
                    self.add_error("password1", exc)
        return data


# ================================================================ Complaint submission
class ComplaintForm(forms.ModelForm):
    """Student form for a new complaint. Hostel and room come from the student's profile."""

    class Meta:
        model = Complaint
        fields = ["title", "category", "priority", "description", "image"]
        labels = {"title": "Subject", "image": "Photo"}
        help_texts = {
            "title": "A short summary, for example: No water in the bathroom.",
            "image": "Optional. JPG or PNG up to 5 MB.",
        }
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "What is the problem?", "maxlength": 120}),
            "description": forms.Textarea(attrs={
                "placeholder": "Describe what happened, where, and since when.", "maxlength": 2000, "rows": 6}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only active categories can be chosen
        self.fields["category"].queryset = ComplaintCategory.objects.filter(is_active=True)
        self.fields["category"].empty_label = "Select a category"

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if len(text) < 10:
            raise forms.ValidationError("Please describe the problem in at least 10 characters.")
        return text

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "size") and image.size > MAX_IMAGE_BYTES:
            raise forms.ValidationError("The photo is larger than 5 MB.")
        return image


# ================================================================ Progress updates
STATUS_ORDER = {"PENDING": 0, "IN_PROGRESS": 1, "RESOLVED": 2}


class ComplaintUpdateForm(forms.Form):
    """Post a progress note and (optionally) move the status forward. History is never overwritten."""

    status = forms.ChoiceField(label="Status after this update")
    message = forms.CharField(
        label="Update note",
        min_length=3,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": 1000, "placeholder": "What has been done or what happens next?"}),
    )

    def __init__(self, *args, complaint=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Status can stay the same or move forward, never backwards
        current = STATUS_ORDER[complaint.status]
        self.fields["status"].choices = [
            (value, label) for value, label in Complaint.Status.choices if STATUS_ORDER[value] >= current
        ]
        self.fields["status"].initial = complaint.status


class AssignForm(forms.Form):
    """Warden or admin chooses the maintenance technician for a complaint."""

    technician = forms.ModelChoiceField(queryset=CustomUser.objects.none(), label="Technician")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["technician"].queryset = CustomUser.objects.filter(
            role=CustomUser.Role.STAFF, is_active=True, is_approved=True
        ).order_by("first_name", "email")


# ================================================================ Profile
class ProfileForm(forms.ModelForm):
    """Users can edit their own name and phone number."""

    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "phone"]


class StyledPasswordChangeForm(PasswordChangeForm):
    """Password change form with autocomplete hints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs["autocomplete"] = "current-password"
        self.fields["new_password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["new_password2"].widget.attrs["autocomplete"] = "new-password"


# ================================================================ Admin: users
class AdminUserForm(forms.ModelForm):
    """Administrator creates or edits any account. Password is only asked for on creation."""

    password1 = forms.CharField(label="Password", required=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirm password", required=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = CustomUser
        fields = ["email", "first_name", "last_name", "phone", "role", "hostel", "is_active", "is_approved"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["hostel"].queryset = Hostel.objects.filter(is_active=True) | Hostel.objects.filter(
            pk=getattr(self.instance, "hostel_id", None)
        )
        self.fields["hostel"].required = False
        self.fields["hostel"].empty_label = "No hostel"
        self.is_create = self.instance.pk is None
        if self.is_create:
            self.fields["password1"].required = True
            self.fields["password2"].required = True
        else:
            self.fields["password1"].label = "New password (leave blank to keep the current one)"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        clash = CustomUser.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email

    def clean(self):
        data = super().clean()
        role, hostel = data.get("role"), data.get("hostel")
        if role in (CustomUser.Role.STUDENT, CustomUser.Role.WARDEN) and not hostel:
            self.add_error("hostel", "Students and wardens must be linked to a hostel.")
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 or p2:
            if p1 != p2:
                self.add_error("password2", "The two passwords do not match.")
            else:
                try:
                    password_validation.validate_password(p1, self.instance)
                except forms.ValidationError as exc:
                    self.add_error("password1", exc)
        return data


# ================================================================ Admin: hostels and categories
class HostelForm(forms.ModelForm):
    class Meta:
        model = Hostel
        fields = ["name", "gender_type", "is_active"]
        labels = {"gender_type": "Hostel type"}


class CategoryForm(forms.ModelForm):
    class Meta:
        model = ComplaintCategory
        fields = ["name", "description", "allows_technician", "is_active"]
        labels = {"allows_technician": "Can be assigned to maintenance staff"}
