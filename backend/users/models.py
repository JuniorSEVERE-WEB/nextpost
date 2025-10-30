from django.contrib.auth.models import AbstractUser
from django.db import models
from .managers import UserManager

class User(AbstractUser):
    """
    Utilisateur custom : authentification par email (unique), pas de username visible.
    """
    username = None
    email = models.EmailField(unique=True)

    # champs de profil basiques (extensibles plus tard)
    full_name = models.CharField(max_length=150, blank=True, default="")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email
