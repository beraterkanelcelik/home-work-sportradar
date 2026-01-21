"""
User model for account management.
"""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from app.core.encryption import encrypt_value, decrypt_value


class UserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier."""
    
    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user with the given email and password."""
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a superuser with the given email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Extended user model with additional fields."""
    
    username = None  # Remove username field
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    token_usage_count = models.BigIntegerField(
        default=0,
        help_text="Cumulative total token usage. This value is incremented when tokens are used and NEVER decreases, even when chats are deleted. This is the source of truth for all-time token usage."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Encrypted API keys (stored encrypted, never in plaintext)
    _openai_api_key = models.TextField(
        blank=True,
        default='',
        db_column='openai_api_key_encrypted',
        help_text="Encrypted OpenAI API key"
    )
    _langfuse_public_key = models.TextField(
        blank=True,
        default='',
        db_column='langfuse_public_key_encrypted',
        help_text="Encrypted Langfuse public key"
    )
    _langfuse_secret_key = models.TextField(
        blank=True,
        default='',
        db_column='langfuse_secret_key_encrypted',
        help_text="Encrypted Langfuse secret key"
    )

    api_keys_validated = models.BooleanField(
        default=False,
        help_text="Whether the current API key bundle was validated successfully",
    )
    api_keys_validated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the last successful API key validation",
    )
    
    # Use email as username
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # email is already in USERNAME_FIELD
    
    objects = UserManager()  # Use custom manager
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.email
    
    def get_full_name(self):
        """Return the full name of the user."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.email
    
    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name or self.email
    
    def increment_token_usage(self, count=1):
        """
        Increment token usage count.

        This method should be called whenever tokens are used. The count is cumulative
        and never decreases, ensuring accurate all-time token tracking even when
        individual chats or sessions are deleted.

        Args:
            count: Number of tokens to add (default: 1)
        """
        self.token_usage_count += count
        self.save(update_fields=['token_usage_count'])

    # Property accessors for encrypted API keys
    @property
    def openai_api_key(self) -> str:
        """Get decrypted OpenAI API key."""
        if not self._openai_api_key:
            return ''
        try:
            return decrypt_value(self._openai_api_key)
        except ValueError:
            return ''

    @openai_api_key.setter
    def openai_api_key(self, value: str):
        """Set and encrypt OpenAI API key."""
        if not value:
            self._openai_api_key = ''
        else:
            self._openai_api_key = encrypt_value(value)

    @property
    def langfuse_public_key(self) -> str:
        """Get decrypted Langfuse public key."""
        if not self._langfuse_public_key:
            return ''
        try:
            return decrypt_value(self._langfuse_public_key)
        except ValueError:
            return ''

    @langfuse_public_key.setter
    def langfuse_public_key(self, value: str):
        """Set and encrypt Langfuse public key."""
        if not value:
            self._langfuse_public_key = ''
        else:
            self._langfuse_public_key = encrypt_value(value)

    @property
    def langfuse_secret_key(self) -> str:
        """Get decrypted Langfuse secret key."""
        if not self._langfuse_secret_key:
            return ''
        try:
            return decrypt_value(self._langfuse_secret_key)
        except ValueError:
            return ''

    @langfuse_secret_key.setter
    def langfuse_secret_key(self, value: str):
        """Set and encrypt Langfuse secret key."""
        if not value:
            self._langfuse_secret_key = ''
        else:
            self._langfuse_secret_key = encrypt_value(value)

    def has_custom_openai_key(self) -> bool:
        """Check if user has a custom OpenAI API key set."""
        return bool(self._openai_api_key)

    def has_custom_langfuse_keys(self) -> bool:
        """Check if user has both Langfuse keys set."""
        return bool(self._langfuse_public_key and self._langfuse_secret_key)

    def clear_api_keys(self):
        """Clear all custom API keys."""
        self._openai_api_key = ''
        self._langfuse_public_key = ''
        self._langfuse_secret_key = ''
        self.api_keys_validated = False
        self.api_keys_validated_at = None
        self.save(update_fields=[
            '_openai_api_key',
            '_langfuse_public_key',
            '_langfuse_secret_key',
            'api_keys_validated',
            'api_keys_validated_at',
        ])
