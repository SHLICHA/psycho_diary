import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test import Client
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()

# Create API client
api_client = APIClient()

# Register
register_response = api_client.post(
    "/api/v1/auth/register/",
    {
        "email": "entry_test@example.com",
        "password": "testpass456",
        "password_confirm": "testpass456",
        "username": "entry_test_user",
    },
    format="json",
)
print(f"Register status: {register_response.status_code}")
if register_response.status_code == status.HTTP_201_CREATED:
    access_token = register_response.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    
    # Create entry
    create_response = api_client.post(
        "/api/v1/entries/",
        {
            "text": "Сегодня я осознал важность баланса между работой и отдыхом",
            "language": "ru",
        },
        format="json",
    )
    print(f"Entry create status: {create_response.status_code}")
    print(f"Entry response data: {create_response.data}")
else:
    print(f"Register error: {register_response.data}")
