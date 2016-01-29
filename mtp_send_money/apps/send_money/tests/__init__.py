from django.utils.crypto import get_random_string
from moj_auth.api_client import REQUEST_TOKEN_URL

from send_money.utils import lenient_unserialise_date


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


def split_prisoner_dob_for_post(data):
    """
    Test helper to split the `prisoner_dob` into POST parameters
    as expected by the `SplitDateField` field
    """
    try:
        prisoner_dob = lenient_unserialise_date(data.pop('prisoner_dob'))
        new_data = data.copy()
        new_data.update({
            'prisoner_dob_0': prisoner_dob.day,
            'prisoner_dob_1': prisoner_dob.month,
            'prisoner_dob_2': prisoner_dob.year,
        })
    except (KeyError, ValueError):
        return data
    return new_data
