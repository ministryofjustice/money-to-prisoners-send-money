from unittest import mock

from django.test import SimpleTestCase
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


def patch_notifications():
    return mock.patch('mtp_common.templatetags.mtp_common.notifications_for_request', mock.Mock(return_value=[]))


def patch_gov_uk_pay_availability_check():
    return mock.patch('send_money.forms.check_payment_service_available',
                      mock.Mock(return_value=(True, None)))


class BaseTestCase(SimpleTestCase):
    root_url = '/en-gb/'

    def assertOnPage(self, response, url_name):  # noqa: N802
        self.assertContains(response, '<!-- %s -->' % url_name)

    def assertResponseNotCacheable(self, response):  # noqa: N802
        self.assertTrue(response.has_header('Cache-Control'), msg='response has no cache control header')
        self.assertIn('no-cache', response['Cache-Control'], msg='response is not private')

    def assertPageNotFound(self, url):  # noqa: N802
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404, msg='should not be able to access %s' % url)
