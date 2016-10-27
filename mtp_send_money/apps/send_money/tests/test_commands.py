from datetime import datetime

from django.core.management import call_command
from django.test import override_settings
from django.test.testcases import SimpleTestCase
import responses

from send_money.tests import mock_auth
from send_money.utils import api_url, govuk_url


@override_settings(GOVUK_PAY_URL='https://pay.gov.local/v1')
class UpdateIncompletePaymentsTestCase(SimpleTestCase):

    @override_settings(ENVIRONMENT='prod')  # because non-prod environments don't send to @outside.local
    def test_confirmation(self):

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/payments/'),
                json={
                    'count': 3,
                    'results': [
                        {
                            'uuid': 'wargle-1111',
                            'processor_id': 1,
                            'recipient_name': 'John',
                            'amount': 1700,
                            'status': 'pending',
                            'created': datetime.now().isoformat() + 'Z',
                        },
                        {
                            'uuid': 'wargle-2222',
                            'processor_id': 2,
                            'recipient_name': 'Tom',
                            'amount': 2000,
                            'status': 'pending',
                            'created': datetime.now().isoformat() + 'Z',
                        },
                        {
                            'uuid': 'wargle-3333',
                            'processor_id': 3,
                            'recipient_name': 'Harry',
                            'amount': 500,
                            'status': 'pending',
                            'created': datetime.now().isoformat() + 'Z',
                        },
                    ]
                },
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % 1),
                json={
                    'state': {'status': 'success'},
                    'email': 'success_sender@outside.local',
                },
                status=200
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % 2),
                json={
                    'state': {'status': 'submitted'},
                    'email': 'pending_sender@outside.local',
                },
                status=200
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % 3),
                json={
                    'state': {'status': 'failed'},
                    'email': 'failed_sender@outside.local',
                },
                status=200
            )
            rsps.add(
                rsps.PATCH,
                api_url('/payments/%s/' % 'wargle-1111'),
                status=200,
            )
            rsps.add(
                rsps.PATCH,
                api_url('/payments/%s/' % 'wargle-3333'),
                status=200,
            )

            call_command('update_incomplete_payments')
