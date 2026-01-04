"""
Script to create a Django superuser non-interactively.
Usage: 
  docker exec django-backend python create_superuser.py <email> <password>
  OR
  docker exec -e DJANGO_SUPERUSER_EMAIL=admin@example.com -e DJANGO_SUPERUSER_PASSWORD=password django-backend python create_superuser.py
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

def create_superuser():
    # Get email and password from command line args or environment variables
    if len(sys.argv) >= 3:
        email = sys.argv[1]
        password = sys.argv[2]
    else:
        email = os.getenv('DJANGO_SUPERUSER_EMAIL')
        password = os.getenv('DJANGO_SUPERUSER_PASSWORD')
    
    if not email:
        print('Error: Email is required.')
        print('Usage: python create_superuser.py <email> <password>')
        print('   OR: Set DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD environment variables')
        sys.exit(1)
    
    if not password:
        print('Error: Password is required.')
        print('Usage: python create_superuser.py <email> <password>')
        print('   OR: Set DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD environment variables')
        sys.exit(1)
    
    if User.objects.filter(email=email).exists():
        print(f'User with email {email} already exists.')
        return
    
    try:
        User.objects.create_superuser(email=email, password=password)
        print(f'Superuser {email} created successfully!')
    except Exception as e:
        print(f'Error creating superuser: {e}')
        sys.exit(1)

if __name__ == '__main__':
    create_superuser()
