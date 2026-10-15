"""Reference data that must always exist: hostels and complaint categories."""

# ---------------------------------------------------------------- Hostels
# (name, gender_type) - gender_type matches Hostel.GENDER_CHOICES
HOSTELS = [
    # Male hostels
    ("Alvan Ikoku Hall", "MALE"),
    ("Eni-Njoku Hall", "MALE"),
    ("Mbanefo Hostel", "MALE"),
    # Female hostels
    ("Aja-Nwachukwu Hostel", "FEMALE"),
    ("Akintola Hall", "FEMALE"),
    ("Akpabio Hall", "FEMALE"),
    ("Awolowo Hall", "FEMALE"),
    ("Balewa Hall", "FEMALE"),
    ("Bello Hall", "FEMALE"),
    ("Eyo Ita Hostel", "FEMALE"),
    ("Isa Kaita Hostel", "FEMALE"),
    ("Kwame Nkrumah Hostel", "FEMALE"),
    ("Mary Slessor Hostel", "FEMALE"),
    ("Okeke Hall", "FEMALE"),
    ("Okpara Hall", "FEMALE"),
    ("Presidential Hostel", "FEMALE"),
    ("TETFund Female Hostel", "FEMALE"),
    # Postgraduate & special hostels
    ("New PG Hostel", "POSTGRAD"),
    ("E-Block Hostel (Nursing Mothers)", "POSTGRAD"),
]

# ---------------------------------------------------------------- Complaint categories
# (name, description, can_be_assigned_to_maintenance_staff)
# These are the only five categories approved for the project.
CATEGORIES = [
    ("Theft", "Stolen or missing belongings.", False),
    ("Facility Issue", "Faulty water, electricity, doors, windows, fans, toilets and similar repairs.", True),
    ("Sexual Abuse", "Sexual harassment or abuse. Handled in confidence by the warden and administrator.", False),
    ("Bullying", "Harassment, intimidation or bullying.", False),
    ("Cult-related Issue", "Suspected cult activity in or around the hostel.", False),
]


def seed_reference_data(using="default"):
    """Create any missing hostels and categories. Safe to run many times."""
    from .models import ComplaintCategory, Hostel

    for name, gender in HOSTELS:
        Hostel.objects.using(using).get_or_create(name=name, defaults={"gender_type": gender})
    for name, description, technician in CATEGORIES:
        ComplaintCategory.objects.using(using).get_or_create(
            name=name,
            defaults={"description": description, "allows_technician": technician},
        )
