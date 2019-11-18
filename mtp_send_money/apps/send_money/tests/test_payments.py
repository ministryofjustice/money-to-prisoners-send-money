from unittest import mock

from django.core import mail
from django.test import override_settings
from django.test.testcases import SimpleTestCase
from mtp_common.test_utils import silence_logger
from requests.exceptions import HTTPError
import responses

from send_money.payments import PaymentClient, PaymentStatus
from send_money.tests import mock_auth
from send_money.utils import api_url, govuk_url


@override_settings(
    GOVUK_PAY_URL='https://pay.gov.local/v1',
    ENVIRONMENT='prod',  # because non-prod environments don't send to @outside.local
)
class CaptureGovukPaymentTestCase(SimpleTestCase):
    """
    Tests related to the capture_govuk_payment method.
    """

    def test_capture(self):
        """
        Test that if the govuk payment is in 'capturable' state, the method captures the payment
        and sends a confirmation email to the sender.

        If the method is called again, nothing happen so that to avoid side effects.
        """
        client = PaymentClient()

        payment_id = 'payment-id'
        govuk_payment = {
            'payment_id': payment_id,
            'state': {
                'status': PaymentStatus.capturable.name,
            },
            'email': 'sender@example.com',

        }
        context = {
            'prisoner_name': 'John Doe',
            'amount': 1700,
        }
        with responses.RequestsMock() as rsps:
            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{payment_id}/capture/'),
                status=204,
            )

            returned_status = client.capture_govuk_payment(govuk_payment, context)

        self.assertEqual(returned_status, PaymentStatus.success)
        self.assertEqual(
            govuk_payment['state']['status'],
            PaymentStatus.success.name,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'Send money to someone in prison: your payment was successful',
        )

        # try to capture the payment again, nothing should happen
        client.capture_govuk_payment(govuk_payment, context)
        self.assertEqual(len(mail.outbox), 1)

    def test_do_nothing_if_payment_in_finished_state(self):
        """
        Test that if the govuk payment is already in a finished state, the method doesn't
        do anything.
        """
        finished_statuses = [
            status
            for status in PaymentStatus
            if status.finished()
        ]
        for status in finished_statuses:
            govuk_payment = {
                'payment_id': 'payment-id',
                'state': {
                    'status': status.name,
                },
            }
            context = {}

            client = PaymentClient()
            returned_status = client.capture_govuk_payment(govuk_payment, context)
            self.assertEqual(returned_status, status)

            self.assertEqual(len(mail.outbox), 0)

    def test_do_nothing_if_govukpayment_is_falsy(self):
        """
        Test that if the passed in govuk payment dict is falsy, the method doesn't do anything.
        """
        client = PaymentClient()

        govuk_payment = {}
        context = {}
        returned_status = client.capture_govuk_payment(govuk_payment, context)
        self.assertEqual(returned_status, None)

        self.assertEqual(len(mail.outbox), 0)

    def test_payment_not_found(self):
        """
        Test that if GOV.UK Pay returns 404 when capturing a payment, the method raises an HTTPError.
        """
        client = PaymentClient()

        payment_id = 'invalid'
        govuk_payment = {
            'payment_id': payment_id,
            'state': {
                'status': PaymentStatus.capturable.name,
            },
        }
        context = {}
        with responses.RequestsMock() as rsps:
            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{payment_id}/capture/'),
                status=404,
            )

            with self.assertRaises(HTTPError) as e:
                client.capture_govuk_payment(govuk_payment, context)

            self.assertEqual(
                e.exception.response.status_code,
                404,
            )

    def test_conflict(self):
        """
        Test that if GOV.UK Pay returns 409 when capturing a payment, the method raises an HTTPError.
        """
        client = PaymentClient()

        payment_id = 'invalid'
        govuk_payment = {
            'payment_id': payment_id,
            'state': {
                'status': PaymentStatus.capturable.name,
            },
        }
        context = {}
        with responses.RequestsMock() as rsps:
            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{payment_id}/capture/'),
                status=409,
            )

            with self.assertRaises(HTTPError) as e:
                client.capture_govuk_payment(govuk_payment, context)

            self.assertEqual(
                e.exception.response.status_code,
                409,
            )


@override_settings(
    GOVUK_PAY_URL='https://pay.gov.local/v1',
    ENVIRONMENT='prod',  # because non-prod environments don't send to @outside.local
)
class CompletePaymentIfNecessaryTestCase(SimpleTestCase):
    """
    Tests related to the complete_payment_if_necessary method.
    """

    def test_success_status(self):
        """
        Test that if the govuk payment is in 'success' state and the MTP payment record
        doesn't have the email field filled in:

        - the MTP payment record is patched with the email value
        - an confirmation email is sent to the sender
        - the method returns PaymentStatus.success
        """
        client = PaymentClient()

        payment = {
            'uuid': 'some-id',
        }
        govuk_payment = {
            'payment_id': 'payment-id',
            'state': {
                'status': PaymentStatus.success.name,
            },
            'email': 'sender@example.com',
        }
        context = {
            'prisoner_name': 'John Doe',
            'amount': 1700,
        }
        with responses.RequestsMock() as rsps:
            mock_auth(rsps)

            # API call related to updating the email address on the payment record
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{payment["uuid"]}/'),
                status=200,
            )

            status = client.complete_payment_if_necessary(payment, govuk_payment, context)

        self.assertEqual(status, PaymentStatus.success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(payment['email'], 'sender@example.com')

    def test_success_status_with_email_already_set(self):
        """
        Test that if the govuk payment is in 'success' state and the MTP payment record
        already has the email field filled in:

        - the method returns PaymentStatus.success

        No email is sent as the email field was already filled in.
        """
        client = PaymentClient()

        payment = {
            'uuid': 'some-id',
            'email': 'some-sender@example.com',
        }
        govuk_payment = {
            'payment_id': 'payment-id',
            'state': {
                'status': PaymentStatus.success.name,
            },
            'email': 'sender@example.com',
        }
        context = {
            'prisoner_name': 'John Doe',
            'amount': 1700,
        }

        status = client.complete_payment_if_necessary(payment, govuk_payment, context)

        self.assertEqual(status, PaymentStatus.success)
        self.assertEqual(len(mail.outbox), 0)

    def test_capturable_status_not_automatically_captured(self):
        """
        Test that if the govuk payment is in 'capturable' state, the MTP payment record
        doesn't have the email field filled in and the payment should not be automatically captured:

        - the MTP payment record is patched with the email value
        - the method returns PaymentStatus.capturable
        - no email is sent
        """
        client = PaymentClient()

        payment = {
            'uuid': 'some-id',
        }
        govuk_payment = {
            'payment_id': 'payment-id',
            'state': {
                'status': PaymentStatus.capturable.name,
            },
            'email': 'sender@example.com',
        }
        context = {
            'prisoner_name': 'John Doe',
            'amount': 1700,
        }

        with \
                mock.patch.object(client, 'should_be_automatically_captured', return_value=False), \
                responses.RequestsMock() as rsps:

            mock_auth(rsps)

            # API call related to updating the email address on the payment record
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{payment["uuid"]}/'),
                status=200,
            )

            status = client.complete_payment_if_necessary(payment, govuk_payment, context)

        self.assertEqual(status, PaymentStatus.capturable)
        self.assertEqual(len(mail.outbox), 0)

    def test_capturable_status_automatically_captured(self):
        """
        Test that if the govuk payment is in 'capturable' state, the MTP payment record
        doesn't have the email field filled in and the payment should be automatically captured:

        - the method captures the payment
        - the MTP payment record is patched with the email value
        - a confirmation email is sent
        - the method returns PaymentStatus.success
        """
        client = PaymentClient()

        payment = {
            'uuid': 'some-id',
        }
        govuk_payment = {
            'payment_id': 'payment-id',
            'state': {
                'status': PaymentStatus.capturable.name,
            },
            'email': 'sender@example.com',
        }
        context = {
            'prisoner_name': 'John Doe',
            'amount': 1700,
        }

        with \
                mock.patch.object(client, 'should_be_automatically_captured', return_value=True), \
                responses.RequestsMock() as rsps:

            mock_auth(rsps)

            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{govuk_payment["payment_id"]}/capture/'),
                status=204,
            )

            # API call related to updating the email address on the payment record
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{payment["uuid"]}/'),
                status=200,
            )

            status = client.complete_payment_if_necessary(payment, govuk_payment, context)

        self.assertEqual(status, PaymentStatus.success)
        self.assertEqual(len(mail.outbox), 1)

    def test_dont_send_email(self):
        """
        Test that the method only sends any email if:
        - the govuk payment status is 'success' and the MTP payment didn't have the email field set
        - the govuk payment status is 'capturable' and the payment should be automatically captured.
        """
        client = PaymentClient()

        payment = {
            'uuid': 'some-id',
        }
        context = {}

        statuses = [
            status
            for status in PaymentStatus
            if status != PaymentStatus.success
        ]

        with \
                mock.patch.object(client, 'should_be_automatically_captured', return_value=False), \
                responses.RequestsMock() as rsps, \
                silence_logger():

            # the 'capturable' status triggers an update on payment.email
            mock_auth(rsps)
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{payment["uuid"]}/'),
                status=200,
            )

            for status in statuses:
                govuk_payment = {
                    'payment_id': 'payment-id',
                    'state': {
                        'status': status.name,

                        # for status == 'errors'
                        'code': 'code',
                        'message': 'message',
                    },
                    'email': 'sender@example.com',
                }
                actual_status = client.complete_payment_if_necessary(payment, govuk_payment, context)

                self.assertEqual(actual_status, status)
                self.assertEqual(len(mail.outbox), 0)

    def test_do_nothing_if_govukpayment_is_falsy(self):
        """
        Test that if the passed in govuk payment dict is falsy, the method returns None and
        doesn't send any email.
        """
        client = PaymentClient()

        payment = {}
        govuk_payment = {}
        context = {}
        status = client.complete_payment_if_necessary(payment, govuk_payment, context)

        self.assertEqual(status, None)
        self.assertEqual(len(mail.outbox), 0)
