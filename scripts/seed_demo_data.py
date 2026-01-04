#!/usr/bin/env python
"""
Seed demo data script.
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
django.setup()

# TODO: Implement demo data seeding
# - Create demo users
# - Create demo documents
# - Create demo chat sessions

if __name__ == '__main__':
    print("Seeding demo data...")
    # TODO: Implement seeding logic
    print("Demo data seeded successfully!")
