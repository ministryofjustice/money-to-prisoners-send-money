from unittest import mock

from django.utils.crypto import get_random_string
from mtp_common.auth.api_client import get_request_token_url


def mock_auth(rsps):
    """
    Adds a mocked response for OAuth authentication
    """
    rsps.add(
        rsps.POST,
        get_request_token_url(),
        json={
            'access_token': get_random_string(length=30),
            'refresh_token': get_random_string(length=30),
        },
        status=200,
    )


def patch_gov_uk_pay_availability_check():
    return mock.patch('send_money.forms.check_payment_service_available',
                      mock.Mock(return_value=(True, None)))


def patch_govuk_pay_connection_check():
    return mock.patch('send_money.views.can_load_govuk_pay_image', mock.Mock(return_value=(True, None)))
