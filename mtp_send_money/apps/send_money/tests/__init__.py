from functools import wraps
from importlib import reload
import sys

from django.conf import settings
from django.core.urlresolvers import clear_url_caches, set_urlconf
from django.utils.crypto import get_random_string
from mtp_common.auth.api_client import REQUEST_TOKEN_URL

from send_money.utils import lenient_unserialise_date, serialise_date


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


def normalise_prisoner_details(prisoner_details):
    """
    Normalises the input prisoner details into the canonical form
    in the form that the API would provide.
    """
    prisoner_details['prisoner_number'] = prisoner_details['prisoner_number'].upper()
    prisoner_details['prisoner_dob'] = serialise_date(
        lenient_unserialise_date(prisoner_details['prisoner_dob'])
    )
    return prisoner_details


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
        return new_data
    except (KeyError, ValueError):
        return data


def update_post_with_prisoner_details(data, prisoner_details):
    """
    Test helper to update POST parameters with prisoner details if necessary
    (prisoner details is then normalised to be the API response)
    """
    required_keys = {'prisoner_number', 'prisoner_dob_0', 'prisoner_dob_1', 'prisoner_dob_2'}
    if required_keys.issubset(data.keys()):
        return
    data.update(split_prisoner_dob_for_post(prisoner_details))


def reload_payment_urls(show_bank_transfer=False, show_debit_card=False):
    def inner(test_func):
        @wraps(test_func)
        def wrapper(self, *args, **kwargs):
            def reload_urls():
                try:
                    reload(sys.modules['send_money.urls'])
                    reload(sys.modules[settings.ROOT_URLCONF])
                except KeyError:
                    pass
                clear_url_caches()
                set_urlconf(None)

            with self.settings(SHOW_BANK_TRANSFER_OPTION=show_bank_transfer,
                               SHOW_DEBIT_CARD_OPTION=show_debit_card):
                reload_urls()
                test_func(self, *args, **kwargs)
            reload_urls()
        return wrapper
    return inner
