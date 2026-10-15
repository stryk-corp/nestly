"""All Nestly views. Access control is enforced here, on the server, for every role."""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import (AdminUserForm, AssignForm, CategoryForm, ComplaintForm, ComplaintUpdateForm,
                    HostelForm, ProfileForm, RegistrationForm, StyledPasswordChangeForm)
from .models import (Complaint, ComplaintCategory, ComplaintUpdate, CustomUser, Hostel,
                     assign_room)

Role = CustomUser.Role
Status = Complaint.Status
PAGE_SIZE = 10


# ================================================================ Helpers
def complaints_for(user):
    """The ONLY place that decides which complaints a user may see (hostel-based access control)."""
    base = Complaint.objects.select_related("student", "hostel", "room", "category", "assigned_to")
    if user.role == Role.ADMIN:
        return base                                   # institution-wide
    if user.role == Role.WARDEN:
        return base.filter(hostel_id=user.hostel_id) if user.hostel_id else base.none()
    if user.role == Role.STAFF:
        return base.filter(assigned_to=user)          # only work assigned to this technician
    if user.role == Role.STUDENT:
        return base.filter(student=user)              # only their own complaints
    return base.none()


def get_stats(qs):
    """Counts shown on dashboard cards."""
    return qs.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=Status.PENDING)),
        in_progress=Count("id", filter=Q(status=Status.IN_PROGRESS)),
        resolved=Count("id", filter=Q(status=Status.RESOLVED)),
    )


def apply_filters(qs, params, allow_hostel=False):
    """Filter a complaint queryset by status, category, priority, (hostel) and a search term."""
    status, category, priority = params.get("status", ""), params.get("category", ""), params.get("priority", "")
    q = params.get("q", "").strip()
    if status in Status.values:
        qs = qs.filter(status=status)
    if category.isdigit():
        qs = qs.filter(category_id=int(category))
    if priority in Complaint.Priority.values:
        qs = qs.filter(priority=priority)
    if allow_hostel and params.get("hostel", "").isdigit():
        qs = qs.filter(hostel_id=int(params["hostel"]))
    if q:
        term = Q(title__icontains=q) | Q(student__first_name__icontains=q) | Q(student__last_name__icontains=q) \
            | Q(student__email__icontains=q)
        if q.lstrip("#").isdigit():
            term |= Q(pk=int(q.lstrip("#")))
        qs = qs.filter(term)
    return qs


def paginate(request, qs):
    """Return (page_obj, querystring-without-page) so filters survive paging."""
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


def add_update(complaint, user, message, status):
    """Append a history row and keep the complaint's current status in step with it."""
    ComplaintUpdate.objects.create(complaint=complaint, updated_by=user, message=message, status_changed_to=status)
    if status != complaint.status:
        complaint.status = status
        complaint.resolved_at = timezone.now() if status == Status.RESOLVED else None
    complaint.save(update_fields=["status", "resolved_at", "updated_at"])


# ================================================================ Public pages
def home(request):
    """Landing page with live totals."""
    return render(request, "landing/home.html", {
        "students_count": CustomUser.objects.filter(role=Role.STUDENT).count(),
        "hostels_count": Hostel.objects.filter(is_active=True).count(),
        "complaints_resolved": Complaint.objects.filter(status=Status.RESOLVED).count(),
    })


def register(request):
    """Sign-up for students, wardens and maintenance staff."""
    if request.user.is_authenticated:
        return redirect("landing:dashboard")

    hostels = Hostel.objects.filter(is_active=True)
    role = request.POST.get("role", Role.STUDENT)
    hostel_id = request.POST.get("hostel_id", "")
    form = RegistrationForm(request.POST or None)

    if request.method == "POST":
        hostel = hostels.filter(pk=hostel_id).first() if hostel_id.isdigit() else None
        role_ok = role in (Role.STUDENT, Role.WARDEN, Role.STAFF)  # admin accounts are never self-registered
        valid = form.is_valid()
        if not role_ok:
            form.add_error(None, "Please choose a valid role.")
        elif role != Role.STAFF and hostel is None:
            form.add_error(None, "Please select your hostel.")
        if valid and role_ok and (role == Role.STAFF or hostel):
            data = form.cleaned_data
            # Students are active at once; wardens and staff wait for administrator approval
            approved = role == Role.STUDENT
            user = CustomUser.objects.create_user(
                email=data["email"], password=data["password1"], first_name=data["first_name"],
                last_name=data["last_name"], phone=data["phone"], role=role,
                hostel=None if role == Role.STAFF else hostel, is_approved=approved,
            )
            if role == Role.STUDENT:
                user.room = assign_room(hostel)  # automatic room link
                user.save(update_fields=["room"])
                login(request, user)
                messages.success(request, "Your account is ready. Welcome to Nestly!")
                return redirect("landing:dashboard")
            messages.success(request, "Account created. An administrator must approve it before you can sign in.")
            return redirect("landing:login")

    return render(request, "landing/register.html", {
        "form": form, "hostels": hostels, "selected_role": role, "selected_hostel": hostel_id,
    })


def user_login(request):
    """Email + password sign-in."""
    if request.user.is_authenticated:
        return redirect("landing:dashboard")

    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        user = authenticate(request, username=email, password=request.POST.get("password", ""))
        if user is None:
            messages.error(request, "Incorrect email or password.")
        elif not user.is_approved:
            messages.warning(request, "Your account is waiting for administrator approval.")
        else:
            login(request, user)
            if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
                return redirect(nxt)
            return redirect("landing:dashboard")
    return render(request, "landing/login.html", {"next": nxt})


def user_logout(request):
    """Sign out (POST only, so a stray link cannot log anyone out)."""
    if request.method == "POST":
        logout(request)
        messages.success(request, "You have been signed out.")
    return redirect("landing:home")


# ================================================================ Role router and profile
@login_required
def dashboard(request):
    """Send each user to the dashboard for their role."""
    user = request.user
    if not user.is_approved:
        logout(request)
        messages.warning(request, "Your account is waiting for administrator approval.")
        return redirect("landing:login")
    target = {Role.STUDENT: "student-dashboard", Role.WARDEN: "warden-dashboard",
              Role.STAFF: "staff-dashboard", Role.ADMIN: "admin-dashboard"}.get(user.role, "home")
    return redirect(f"landing:{target}")


@login_required
def profile(request):
    """View and edit your own details; change your password."""
    user = request.user
    profile_form = ProfileForm(instance=user)
    password_form = StyledPasswordChangeForm(user)
    if request.method == "POST":
        if request.POST.get("form") == "password":
            password_form = StyledPasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)  # stay signed in
                messages.success(request, "Password changed.")
                return redirect("landing:profile")
        else:
            profile_form = ProfileForm(request.POST, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated.")
                return redirect("landing:profile")
    return render(request, "landing/profile.html", {
        "profile_form": profile_form, "password_form": password_form, "active": "profile",
    })


# ================================================================ Student
@role_required(Role.STUDENT)
def student_dashboard(request):
    """The student's own complaints with status counts."""
    qs = complaints_for(request.user)
    page_obj, _ = paginate(request, qs)
    return render(request, "landing/student_dashboard.html", {"page_obj": page_obj, "stats": get_stats(qs)})


@role_required(Role.STUDENT)
def submit_complaint(request):
    """Create a complaint linked to the student's hostel and room, with an initial history entry."""
    user = request.user
    if not user.hostel_id:
        messages.error(request, "Your account has no hostel yet. Ask the administrator to link you to one.")
        return redirect("landing:student-dashboard")

    form = ComplaintForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        complaint = form.save(commit=False)
        complaint.student, complaint.hostel, complaint.room = user, user.hostel, user.room
        complaint.status = Status.PENDING
        complaint.save()
        ComplaintUpdate.objects.create(complaint=complaint, updated_by=user,
                                       message="Complaint submitted.", status_changed_to=Status.PENDING)
        messages.success(request, f"Complaint #{complaint.pk} submitted. Its status is Pending.")
        return redirect("landing:view-complaint", pk=complaint.pk)
    return render(request, "landing/submit_complaint.html", {"form": form})


@role_required(Role.STUDENT)
def view_complaint(request, pk):
    """A student's complaint with its full update history."""
    complaint = get_object_or_404(complaints_for(request.user), pk=pk)
    updates = complaint.updates.select_related("updated_by")
    return render(request, "landing/complaint_detail.html", {"complaint": complaint, "updates": updates})


@role_required(Role.STUDENT)
def rate_complaint(request, pk):
    """Student rates a resolved complaint (once)."""
    complaint = get_object_or_404(complaints_for(request.user), pk=pk)
    if complaint.status != Status.RESOLVED or complaint.student_rating:
        messages.info(request, "This complaint cannot be rated right now.")
        return redirect("landing:view-complaint", pk=pk)
    if request.method == "POST":
        rating = request.POST.get("rating", "")
        if rating in ("1", "2", "3", "4", "5"):
            complaint.student_rating = int(rating)
            complaint.student_feedback = request.POST.get("feedback", "").strip()[:500]
            complaint.save(update_fields=["student_rating", "student_feedback", "updated_at"])
            messages.success(request, "Thank you for your feedback.")
            return redirect("landing:view-complaint", pk=pk)
        messages.error(request, "Choose a rating from 1 to 5 stars.")
    return render(request, "landing/rate_complaint.html", {"complaint": complaint})


# ================================================================ Shared complaint handling (warden, staff, admin)
def handle_complaint(request, complaint, can_assign, update_action, assign_action, back_url, template_active):
    """Show a complaint to staff-side users and process update / assign POSTs."""
    user = request.user
    update_form = ComplaintUpdateForm(complaint=complaint)
    assign_form = AssignForm()

    if request.method == "POST":
        action = request.POST.get("action", "update")
        if action == "assign" and can_assign:
            assign_form = AssignForm(request.POST)
            if not complaint.category.allows_technician:
                messages.error(request, "Only facility issues can be assigned to maintenance staff.")
            elif assign_form.is_valid():
                tech = assign_form.cleaned_data["technician"]
                complaint.assigned_to = tech
                complaint.save(update_fields=["assigned_to", "updated_at"])
                add_update(complaint, user, f"Assigned to {tech}.", complaint.status)
                messages.success(request, f"Assigned to {tech}.")
                return redirect(request.path)
        elif action == "update":
            update_form = ComplaintUpdateForm(request.POST, complaint=complaint)
            if update_form.is_valid():
                add_update(complaint, user, update_form.cleaned_data["message"], update_form.cleaned_data["status"])
                messages.success(request, "Update posted.")
                return redirect(request.path)

    return render(request, "landing/complaint_manage.html", {
        "complaint": complaint,
        "updates": complaint.updates.select_related("updated_by"),
        "update_form": update_form,
        "assign_form": assign_form,
        "can_assign": can_assign and complaint.category.allows_technician,
        "update_action": update_action,
        "assign_action": assign_action,
        "back_url": back_url,
        "active": template_active,
    })


# ================================================================ Warden
@role_required(Role.WARDEN)
def warden_dashboard(request):
    """Complaints for the warden's own hostel only."""
    user = request.user
    scope = complaints_for(user)
    page_obj, qs = paginate(request, apply_filters(scope, request.GET))
    return render(request, "landing/warden_dashboard.html", {
        "page_obj": page_obj, "qs": qs, "stats": get_stats(scope), "categories": ComplaintCategory.objects.all(),
        "filters": request.GET, "detail_url": "landing:manage-complaint", "active": "dashboard",
    })


@role_required(Role.WARDEN)
def manage_complaint(request, pk):
    """Warden reviews a complaint in their hostel, posts updates and assigns a technician."""
    complaint = get_object_or_404(complaints_for(request.user), pk=pk)  # 404 for other hostels
    url = reverse("landing:manage-complaint", args=[pk])
    return handle_complaint(request, complaint, True, url, url, reverse("landing:warden-dashboard"), "dashboard")


# ================================================================ Staff (maintenance technicians)
@role_required(Role.STAFF)
def staff_dashboard(request):
    """Complaints assigned to this technician."""
    scope = complaints_for(request.user)
    page_obj, qs = paginate(request, apply_filters(scope, request.GET))
    return render(request, "landing/staff_dashboard.html", {
        "page_obj": page_obj, "qs": qs, "stats": get_stats(scope), "categories": ComplaintCategory.objects.all(),
        "filters": request.GET, "detail_url": "landing:view-complaint-staff", "active": "dashboard",
    })


@role_required(Role.STAFF)
def view_complaint_staff(request, pk):
    """A technician opens one of their assigned complaints."""
    complaint = get_object_or_404(complaints_for(request.user), pk=pk)
    update_url = reverse("landing:update-complaint-status", args=[pk])
    return handle_complaint(request, complaint, False, update_url, "", reverse("landing:staff-dashboard"), "dashboard")


@role_required(Role.STAFF)
@require_POST
def update_complaint_status(request, pk):
    """A technician posts progress and updates the status."""
    complaint = get_object_or_404(complaints_for(request.user), pk=pk)
    form = ComplaintUpdateForm(request.POST, complaint=complaint)
    if form.is_valid():
        add_update(complaint, request.user, form.cleaned_data["message"], form.cleaned_data["status"])
        messages.success(request, "Update posted.")
        return redirect("landing:view-complaint-staff", pk=pk)
    update_url = reverse("landing:update-complaint-status", args=[pk])
    return render(request, "landing/complaint_manage.html", {
        "complaint": complaint, "updates": complaint.updates.select_related("updated_by"),
        "update_form": form, "assign_form": AssignForm(), "can_assign": False, "update_action": update_url,
        "assign_action": "", "back_url": reverse("landing:staff-dashboard"), "active": "dashboard",
    })


# ================================================================ Administrator
@role_required(Role.ADMIN)
def admin_dashboard(request):
    """Institution-wide overview with hostel, category and status filters."""
    scope = complaints_for(request.user)
    page_obj, qs = paginate(request, apply_filters(scope, request.GET, allow_hostel=True))
    per_hostel = Hostel.objects.annotate(
        total=Count("complaints"),
        pending=Count("complaints", filter=Q(complaints__status=Status.PENDING)),
        in_progress=Count("complaints", filter=Q(complaints__status=Status.IN_PROGRESS)),
        resolved=Count("complaints", filter=Q(complaints__status=Status.RESOLVED)),
    ).order_by("-total", "name")
    return render(request, "landing/admin_dashboard.html", {
        "page_obj": page_obj, "qs": qs, "stats": get_stats(scope), "per_hostel": per_hostel,
        "hostels": Hostel.objects.all(), "categories": ComplaintCategory.objects.all(),
        "filters": request.GET, "detail_url": "landing:admin-complaint", "active": "dashboard",
        "awaiting_approval": CustomUser.objects.filter(is_approved=False).count(),
        "user_counts": {r.label: CustomUser.objects.filter(role=r.value).count() for r in Role},
    })


@role_required(Role.ADMIN)
def admin_complaint(request, pk):
    """Administrator opens any complaint, reads its history and can post updates or assign staff."""
    complaint = get_object_or_404(complaints_for(request.user), pk=pk)
    url = reverse("landing:admin-complaint", args=[pk])
    return handle_complaint(request, complaint, True, url, url, reverse("landing:admin-dashboard"), "dashboard")


# ---------------------------------------------------------------- Admin: users
@role_required(Role.ADMIN)
def manage_users(request):
    """List, search and filter accounts."""
    users = CustomUser.objects.select_related("hostel", "room").order_by("-date_joined")
    role, state, q = request.GET.get("role", ""), request.GET.get("state", ""), request.GET.get("q", "").strip()
    if role in Role.values:
        users = users.filter(role=role)
    if state == "pending":
        users = users.filter(is_approved=False)
    elif state == "inactive":
        users = users.filter(is_active=False)
    if q:
        users = users.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    page_obj, qs = paginate(request, users)
    return render(request, "landing/manage_users.html", {
        "page_obj": page_obj, "qs": qs, "roles": Role.choices, "filters": request.GET, "active": "users",
        "awaiting_approval": CustomUser.objects.filter(is_approved=False).count(),
    })


@role_required(Role.ADMIN)
def admin_user_form(request, pk=None):
    """Create a user (pk is None) or edit one."""
    user = get_object_or_404(CustomUser, pk=pk) if pk else None
    old_hostel = user.hostel_id if user else None
    form = AdminUserForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if form.cleaned_data.get("password1"):
            obj.set_password(form.cleaned_data["password1"])
        if obj.pk == request.user.pk and (not obj.is_active or obj.role != Role.ADMIN):
            messages.error(request, "You cannot deactivate or demote your own account.")
            return redirect("landing:manage-users")
        if obj.role == Role.STAFF:
            obj.hostel = None
        obj.save()
        # Students get a room in their hostel; moving hostel means a new room
        if obj.role == Role.STUDENT and obj.hostel_id and (obj.room is None or obj.hostel_id != old_hostel or obj.room.hostel_id != obj.hostel_id):
            obj.room = assign_room(obj.hostel)
            obj.save(update_fields=["room"])
        messages.success(request, "User saved.")
        return redirect("landing:manage-users")
    return render(request, "landing/admin_form.html", {
        "form": form, "title": "Edit user" if user else "Add user",
        "intro": "Wardens manage the hostel you choose and see only its complaints.",
        "back_url": reverse("landing:manage-users"), "active": "users",
    })


@role_required(Role.ADMIN)
@require_POST
def admin_user_action(request, pk):
    """Approve, activate or deactivate an account."""
    target = get_object_or_404(CustomUser, pk=pk)
    action = request.POST.get("action")
    if target.pk == request.user.pk and action == "deactivate":
        messages.error(request, "You cannot deactivate your own account.")
    elif action == "approve":
        target.is_approved = True
        target.save(update_fields=["is_approved"])
        messages.success(request, f"{target} approved.")
    elif action == "deactivate":
        target.is_active = False
        target.save(update_fields=["is_active"])
        messages.success(request, f"{target} deactivated.")
    elif action == "activate":
        target.is_active = True
        target.save(update_fields=["is_active"])
        messages.success(request, f"{target} activated.")
    return redirect(request.POST.get("next") if request.POST.get("next", "").startswith("/") else "landing:manage-users")


# ---------------------------------------------------------------- Admin: hostels
@role_required(Role.ADMIN)
def manage_hostels(request):
    """Hostel records with resident, warden and complaint counts."""
    hostels = Hostel.objects.annotate(
        students=Count("members", filter=Q(members__role=Role.STUDENT), distinct=True),
        wardens=Count("members", filter=Q(members__role=Role.WARDEN), distinct=True),
        open_complaints=Count("complaints", filter=~Q(complaints__status=Status.RESOLVED), distinct=True),
        total_complaints=Count("complaints", distinct=True),
    )
    return render(request, "landing/manage_hostels.html", {"hostels": hostels, "active": "hostels"})


@role_required(Role.ADMIN)
def hostel_form(request, pk=None):
    hostel = get_object_or_404(Hostel, pk=pk) if pk else None
    form = HostelForm(request.POST or None, instance=hostel)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Hostel saved.")
        return redirect("landing:manage-hostels")
    return render(request, "landing/admin_form.html", {
        "form": form, "title": "Edit hostel" if hostel else "Add hostel", "intro": "Hostels cannot be deleted, only made inactive, so complaint history stays intact.",
        "back_url": reverse("landing:manage-hostels"), "active": "hostels",
    })


@role_required(Role.ADMIN)
@require_POST
def hostel_toggle(request, pk):
    hostel = get_object_or_404(Hostel, pk=pk)
    hostel.is_active = not hostel.is_active
    hostel.save(update_fields=["is_active"])
    messages.success(request, f"{hostel.name} is now {'active' if hostel.is_active else 'inactive'}.")
    return redirect("landing:manage-hostels")


# ---------------------------------------------------------------- Admin: categories
@role_required(Role.ADMIN)
def manage_categories(request):
    cats = ComplaintCategory.objects.annotate(total=Count("complaints"))
    return render(request, "landing/manage_categories.html", {"categories": cats, "active": "categories"})


@role_required(Role.ADMIN)
def category_form(request, pk=None):
    category = get_object_or_404(ComplaintCategory, pk=pk) if pk else None
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category saved.")
        return redirect("landing:manage-categories")
    return render(request, "landing/admin_form.html", {
        "form": form, "title": "Edit category" if category else "Add category",
        "intro": "The project approves five categories. Add new ones only with approval.",
        "back_url": reverse("landing:manage-categories"), "active": "categories",
    })


@role_required(Role.ADMIN)
@require_POST
def category_toggle(request, pk):
    category = get_object_or_404(ComplaintCategory, pk=pk)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active"])
    messages.success(request, f"{category.name} is now {'active' if category.is_active else 'inactive'}.")
    return redirect("landing:manage-categories")
