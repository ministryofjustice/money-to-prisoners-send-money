from django.core import mail
from django.test import override_settings
from django.test.testcases import SimpleTestCase
from requests.exceptions import HTTPError
import responses

from send_money.exceptions import GovUkPaymentStatusException
from send_money.payments import PaymentClient, PaymentStatus
from send_money.tests import mock_auth
from send_money.utils import api_url, govuk_url


@override_settings(
    GOVUK_PAY_URL='https://pay.gov.local/v1',
    ENVIRONMENT='prod',  # because non-prod environments don't send to @outside.local
)
class CapturePaymentTestCase(SimpleTestCase):
    """
    Tests related to the capture_payment method.
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

            client.capture_payment(govuk_payment, context)

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
        client.capture_payment(govuk_payment, context)
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
            client.capture_payment(govuk_payment, context)

            self.assertEqual(len(mail.outbox), 0)

    def test_do_nothing_if_govukpayment_is_falsy(self):
        """
        Test that if the passed in govuk payment dict is falsy, the method doesn't do anything.
        """
        client = PaymentClient()

        govuk_payment = {}
        context = {}
        client.capture_payment(govuk_payment, context)

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
                client.capture_payment(govuk_payment, context)

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
                client.capture_payment(govuk_payment, context)

            self.assertEqual(
                e.exception.response.status_code,
                409,
            )


@override_settings(
    GOVUK_PAY_URL='https://pay.gov.local/v1',
    ENVIRONMENT='prod',  # because non-prod environments don't send to @outside.local
)
class CheckGovukPaymentStatusTestCase(SimpleTestCase):
    """
    Tests related to the check_govuk_payment_status method.
    """

    def test_success_status(self):
        """
        Test that if the govuk payment is in 'success' state and the MTP payment record
        doesn't have the email field filled in:

        - the method returns PaymentStatus.success
        - the MTP payment record is patched with the email value
        - an confirmation email is sent to the sender
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

            status = client.check_govuk_payment_status(payment, govuk_payment, context)

        self.assertEqual(status, PaymentStatus.success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(payment['email'], 'sender@example.com')

    def test_capturable_status(self):
        """
        Test that if the govuk payment is in 'capturable' state and the MTP payment record
        doesn't have the email field filled in:

        - the method returns PaymentStatus.capturable
        - the MTP payment record is patched with the email value
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
        with responses.RequestsMock() as rsps:
            mock_auth(rsps)

            # API call related to updating the email address on the payment record
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{payment["uuid"]}/'),
                status=200,
            )

            status = client.check_govuk_payment_status(payment, govuk_payment, context)

        self.assertEqual(status, PaymentStatus.capturable)
        self.assertEqual(len(mail.outbox), 0)

    def test_dont_send_email(self):
        """
        Test that if the status of govuk payment != 'success', the method doesn't send any email.
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

        with responses.RequestsMock() as rsps:
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
                actual_status = client.check_govuk_payment_status(payment, govuk_payment, context)

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
        status = client.check_govuk_payment_status(payment, govuk_payment, context)

        self.assertEqual(status, None)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(
    GOVUK_PAY_URL='https://pay.gov.local/v1',
    ENVIRONMENT='prod',  # because non-prod environments don't send to @outside.local
)
class CheckGovukPaymentSucceededTestCase(SimpleTestCase):
    """
    Tests related to the check_govuk_payment_succeeded method.
    """

    def test_returns_true_if_payment_succeeded(self):
        """
        Test that if the govuk payment is in 'success' state and the MTP payment record
        doesn't have the email field filled in:

        - the method returns True
        - the MTP payment record is patched with the email value
        - an confirmation email is sent to the sender
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

            succeeded = client.check_govuk_payment_succeeded(payment, govuk_payment, context)

        self.assertEqual(succeeded, True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(payment['email'], 'sender@example.com')

    def test_returns_false_if_payment_failed(self):
        """
        Test that if the govuk payment is in a finished non-successful state, the method returns
        False and no email is sent.
        """
        client = PaymentClient()

        payment = {
            'uuid': 'some-id',
        }
        context = {}

        statuses = [PaymentStatus.error, PaymentStatus.failed, PaymentStatus.cancelled]
        for status in statuses:
            govuk_payment = {
                'payment_id': 'payment-id',
                'state': {
                    'status': status.name,
                },
                'email': 'sender@example.com',
            }

        succeeded = client.check_govuk_payment_succeeded(payment, govuk_payment, context)

        self.assertEqual(succeeded, False)
        self.assertEqual(len(mail.outbox), 0)

    def test_returns_false_if_govukpayment_is_falsy(self):
        """
        Test that if the passed in govuk payment dict is falsy, the method returns False and
        doesn't send any email.
        """
        client = PaymentClient()

        payment = {}
        govuk_payment = {}
        context = {}
        status = client.check_govuk_payment_succeeded(payment, govuk_payment, context)

        self.assertEqual(status, False)
        self.assertEqual(len(mail.outbox), 0)

    def test_raise_exception_if_status_is_incomplete(self):
        """
        Test that if the govuk payment is in a finished non-successful state, the method returns
        False and no email is sent.
        """
        client = PaymentClient()

        payment = {
            'uuid': 'some-id',
        }
        context = {}

        incomplete_statuses = [
            status
            for status in PaymentStatus
            if not status.finished()
        ]
        for status in incomplete_statuses:
            govuk_payment = {
                'payment_id': 'payment-id',
                'state': {
                    'status': status.name,
                }
            }

            with self.assertRaises(GovUkPaymentStatusException):
                client.check_govuk_payment_succeeded(payment, govuk_payment, context)
