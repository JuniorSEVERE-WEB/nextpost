from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import RegisterView, MeViewSet

urlpatterns = [
    # Auth
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # Register
    path("register/", RegisterView.as_view(), name="register"),

    # Me endpoints
    path("me/", MeViewSet.as_view({"get": "profile"}), name="me-profile"),
    path("me/update/", MeViewSet.as_view({"patch": "update_profile"}), name="me-update"),
]
