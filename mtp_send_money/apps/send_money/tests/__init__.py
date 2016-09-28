from django.utils.crypto import get_random_string
from mtp_common.auth.api_client import REQUEST_TOKEN_URL


def mock_auth(rsps):
    """
    Adds a mocked response for OAuth authentication
    """
    rsps.add(
        rsps.POST,
        REQUEST_TOKEN_URL,
        json={
            'access_token': get_random_string(length=30),
            'refresh_token': get_random_string(length=30),
        },
        status=200,
    )
