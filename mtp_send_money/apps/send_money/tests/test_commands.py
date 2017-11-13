from datetime import datetime
import json
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.test.testcases import SimpleTestCase
from django.utils.timezone import utc
import responses

from send_money.tests import mock_auth
from send_money.utils import api_url, govuk_url


@override_settings(GOVUK_PAY_URL='https://pay.gov.local/v1')
@override_settings(RUN_CLEANUP_TASKS=True)
class UpdateIncompletePaymentsTestCase(SimpleTestCase):

    @override_settings(ENVIRONMENT='prod')  # because non-prod environments don't send to @outside.local
    def test_update_incomplete_payments(self):
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
                            'prisoner_number': 'A1409AE',
                            'prisoner_dob': '1989-01-21'
                        },
                        {
                            'uuid': 'wargle-2222',
                            'processor_id': 2,
                            'recipient_name': 'Tom',
                            'amount': 2000,
                            'status': 'pending',
                            'created': datetime.now().isoformat() + 'Z',
                            'prisoner_number': 'A1234GJ',
                            'prisoner_dob': '1954-04-17'
                        },
                        {
                            'uuid': 'wargle-3333',
                            'processor_id': 3,
                            'recipient_name': 'Harry',
                            'amount': 500,
                            'status': 'pending',
                            'created': datetime.now().isoformat() + 'Z',
                            'prisoner_number': 'A5544CD',
                            'prisoner_dob': '1992-12-05'
                        },
                    ]
                },
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % 1),
                json={
                    'reference': 'wargle-1111',
                    'state': {'status': 'success'},
                    'settlement_summary': {
                        'capture_submit_time': '2016-10-27T15:11:05Z',
                        'captured_date': '2016-10-27'
                    },
                    'email': 'success_sender@outside.local',
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
                api_url('/payments/%s/' % 'wargle-1111'),
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % 2),
                json={
                    'reference': 'wargle-2222',
                    'state': {'status': 'submitted'},
                    'settlement_summary': {
                        'capture_submit_time': '2016-10-27T15:11:05Z',
                        'captured_date': None
                    },
                    'email': 'pending_sender@outside.local',
                },
                status=200
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % 3),
                json={
                    'reference': 'wargle-3333',
                    'state': {'status': 'failed'},
                    'settlement_summary': {
                        'capture_submit_time': None,
                        'captured_date': None
                    },
                    'email': 'failed_sender@outside.local',
                },
                status=200
            )
            rsps.add(
                rsps.PATCH,
                api_url('/payments/%s/' % 'wargle-3333'),
                status=200,
            )

            call_command('update_incomplete_payments')

            self.assertEqual(
                json.loads(rsps.calls[-5].request.body.decode())['email'],
                'success_sender@outside.local'
            )
            self.assertEqual(
                json.loads(rsps.calls[-4].request.body.decode())['received_at'],
                '2016-10-27T15:11:05+00:00'
            )
            self.assertEqual(
                json.loads(rsps.calls[-1].request.body.decode())['status'],
                'failed'
            )

    ref = 'wargle-1111'
    processor_id = '1'
    payment_data = {
        'count': 1,
        'results': [
            {
                'uuid': ref,
                'processor_id': processor_id,
                'recipient_name': 'John',
                'amount': 1700,
                'status': 'pending',
                'email': 'success_sender@outside.local',
                'created': datetime.now().isoformat() + 'Z',
                'prisoner_number': 'A1409AE',
                'prisoner_dob': '1989-01-21'
            }
        ]
    }

    @override_settings(ENVIRONMENT='prod')  # because non-prod environments don't send to @outside.local
    def test_update_incomplete_payments_no_govuk_payment_found(self):
        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/payments/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % self.processor_id),
                status=404
            )
            rsps.add(
                rsps.PATCH,
                api_url('/payments/%s/' % self.ref),
                status=200,
            )

            call_command('update_incomplete_payments')

            self.assertEqual(rsps.calls[3].request.body.decode(), '{"status": "failed"}')

    @override_settings(ENVIRONMENT='prod')  # because non-prod environments don't send to @outside.local
    def test_update_incomplete_payments_doesnt_resend_sent_email(self):
        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/payments/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % self.processor_id),
                json={
                    'reference': self.ref,
                    'state': {'status': 'success'},
                    'settlement_summary': {
                        'capture_submit_time': '2016-10-27T15:11:05Z',
                        'captured_date': '2016-10-27'
                    },
                    'email': 'success_sender@outside.local',
                },
                status=200
            )
            rsps.add(
                rsps.PATCH,
                api_url('/payments/%s/' % self.ref),
                status=200,
            )

            call_command('update_incomplete_payments')

            self.assertEqual(len(mail.outbox), 0)

    @override_settings(ENVIRONMENT='prod')  # because non-prod environments don't send to @outside.local
    def _test_update_incomplete_payments_doesnt_update_before_capture(self, settlement_summary):
        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/payments/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % self.processor_id),
                json={
                    'reference': self.ref,
                    'state': {'status': 'success'},
                    'settlement_summary': settlement_summary,
                    'email': 'success_sender@outside.local',
                },
                status=200
            )

            call_command('update_incomplete_payments')

            self.assertEqual(len(mail.outbox), 0)

    def test_update_incomplete_payments_doesnt_update_with_missing_captured_date(self):
        self._test_update_incomplete_payments_doesnt_update_before_capture({
            'capture_submit_time': '2016-10-27T15:11:05Z',
        })

    def test_update_incomplete_payments_doesnt_update_with_null_capture_time(self):
        self._test_update_incomplete_payments_doesnt_update_before_capture({
            'capture_submit_time': '2016-10-27T15:11:05Z',
            'captured_date': None
        })

    def test_update_incomplete_payments_doesnt_update_with_blank_capture_time(self):
        self._test_update_incomplete_payments_doesnt_update_before_capture({
            'capture_submit_time': '2016-10-27T15:11:05Z',
            'captured_date': ''
        })

    def test_update_incomplete_payments_doesnt_update_with_invalid_capture_time(self):
        self._test_update_incomplete_payments_doesnt_update_before_capture({
            'capture_submit_time': '2016-10-27T15:11:05Z',
            'captured_date': '2015'
        })

    @override_settings(ENVIRONMENT='prod')  # because non-prod environments don't send to @outside.local
    def _test_received_at_date_matches_captured_date(self, capture_submit_time, captured_date, received_at):
        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/payments/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % self.processor_id),
                json={
                    'reference': self.ref,
                    'state': {'status': 'success'},
                    'settlement_summary': {
                        'capture_submit_time': capture_submit_time,
                        'captured_date': captured_date
                    },
                    'email': 'success_sender@outside.local',
                },
                status=200
            )
            rsps.add(
                rsps.PATCH,
                api_url('/payments/%s/' % self.ref),
                status=200,
            )

            call_command('update_incomplete_payments')

            self.assertEqual(
                json.loads(rsps.calls[-1].request.body.decode())['received_at'],
                received_at
            )

    def test_submit_time_used_when_date_the_same(self):
        self._test_received_at_date_matches_captured_date(
            '2016-10-28T14:57:05Z',
            '2016-10-28',
            '2016-10-28T14:57:05+00:00'
        )

    def test_received_at_date_is_put_forward(self):
        self._test_received_at_date_matches_captured_date(
            '2016-10-27T23:57:05Z',
            '2016-10-28',
            '2016-10-28T00:00:00+00:00'
        )

    # Assume captured_date is UTC. May not be a correct assumption, but it's
    # the only one that can work.
    def test_received_at_date_takes_timezones_into_account(self):
        self._test_received_at_date_matches_captured_date(
            '2016-10-28T00:57:05+01:00',
            '2016-10-28',
            '2016-10-28T00:00:00+00:00'
        )

    @mock.patch('mtp_send_money.apps.send_money.payments.timezone.now')
    def test_received_at_date_is_set_to_now_when_submit_time_absent(self, mock_now):
        mock_now.return_value = datetime(2016, 10, 28, 12, 45, 22, tzinfo=utc)
        self._test_received_at_date_matches_captured_date(
            '',
            '2016-10-28',
            '2016-10-28T12:45:22+00:00'
        )

    @mock.patch('mtp_send_money.apps.send_money.payments.timezone.now')
    def test_received_at_date_is_put_back(self, mock_now):
        mock_now.return_value = datetime(2016, 10, 29, 0, 5, 22, tzinfo=utc)
        self._test_received_at_date_matches_captured_date(
            '',
            '2016-10-28',
            '2016-10-28T23:59:59.999999+00:00'
        )
