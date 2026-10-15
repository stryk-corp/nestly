"""Project-level URL routes."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Django's built-in admin site (database-level management)
    path("admin/", admin.site.urls),
    # All Nestly pages live in the landing app
    path("", include("landing.urls")),
]

# Serve uploaded complaint photos while developing
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
