import json
from unittest import mock

from django.core import mail
from django.test import override_settings
from django.test.testcases import SimpleTestCase
from mtp_common.test_utils import silence_logger
from requests.exceptions import HTTPError
import responses

from send_money.payments import CheckResult, PaymentClient, PaymentStatus
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
        and no email is sent.

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
        with responses.RequestsMock() as rsps:
            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{payment_id}/capture/'),
                status=204,
            )

            returned_status = client.capture_govuk_payment(govuk_payment)

        self.assertEqual(returned_status, PaymentStatus.success)
        self.assertEqual(
            govuk_payment['state']['status'],
            PaymentStatus.success.name,
        )

        self.assertEqual(len(mail.outbox), 0)

        # try to capture the payment again, nothing should happen
        client.capture_govuk_payment(govuk_payment)
        self.assertEqual(len(mail.outbox), 0)

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

            client = PaymentClient()
            returned_status = client.capture_govuk_payment(govuk_payment)
            self.assertEqual(returned_status, status)

            self.assertEqual(len(mail.outbox), 0)

    def test_do_nothing_if_govukpayment_is_falsy(self):
        """
        Test that if the passed in govuk payment dict is falsy, the method doesn't do anything.
        """
        client = PaymentClient()

        govuk_payment = {}
        returned_status = client.capture_govuk_payment(govuk_payment)
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
        with responses.RequestsMock() as rsps:
            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{payment_id}/capture/'),
                status=404,
            )

            with self.assertRaises(HTTPError) as e:
                client.capture_govuk_payment(govuk_payment)

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
        with responses.RequestsMock() as rsps:
            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{payment_id}/capture/'),
                status=409,
            )

            with self.assertRaises(HTTPError) as e:
                client.capture_govuk_payment(govuk_payment)

            self.assertEqual(
                e.exception.response.status_code,
                409,
            )


@override_settings(
    GOVUK_PAY_URL='https://pay.gov.local/v1',
    ENVIRONMENT='prod',  # because non-prod environments don't send to @outside.local
)
class CancelGovukPaymentTestCase(SimpleTestCase):
    """
    Tests related to the cancel_govuk_payment method.
    """

    def test_cancel(self):
        """
        Test that if the govuk payment is in 'capturable' state, the method cancels the payment
        and sends an email to the sender.

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
        payment = {
            'uuid': 'b74a0eb6-0437-4b22-bce8-e6f11bd43802',
            'recipient_name': 'Alice Re',
            'prisoner_name': 'John Doe',
            'prisoner_number': 'AAB0A00',
            'amount': 1700,
        }
        with responses.RequestsMock() as rsps:
            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{payment_id}/cancel/'),
                status=204,
            )

            returned_status = client.cancel_govuk_payment(payment, govuk_payment)

        self.assertEqual(returned_status, PaymentStatus.cancelled)
        self.assertEqual(
            govuk_payment['state']['status'],
            PaymentStatus.cancelled.name,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'Send money to someone in prison: your payment has NOT been sent to the prisoner',
        )

        # try to capture the payment again, nothing should happen
        client.cancel_govuk_payment(payment, govuk_payment)
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
        payment = {
            'uuid': 'b74a0eb6-0437-4b22-bce8-e6f11bd43802',
            'recipient_name': 'Alice Re',
            'prisoner_name': 'John Doe',
            'prisoner_number': 'AAB0A00',
            'amount': 1700,
        }
        for status in finished_statuses:
            govuk_payment = {
                'payment_id': 'payment-id',
                'state': {
                    'status': status.name,
                },
            }

            client = PaymentClient()
            returned_status = client.cancel_govuk_payment(payment, govuk_payment)
            self.assertEqual(returned_status, status)

            self.assertEqual(len(mail.outbox), 0)

    def test_do_nothing_if_govukpayment_is_falsy(self):
        """
        Test that if the passed in govuk payment dict is falsy, the method doesn't do anything.
        """
        client = PaymentClient()

        govuk_payment = {}
        payment = {
            'uuid': 'b74a0eb6-0437-4b22-bce8-e6f11bd43802',
            'recipient_name': 'Alice Re',
            'prisoner_name': 'John Doe',
            'prisoner_number': 'AAB0A00',
            'amount': 1700,
        }
        returned_status = client.cancel_govuk_payment(payment, govuk_payment)
        self.assertEqual(returned_status, None)

        self.assertEqual(len(mail.outbox), 0)

    def test_payment_not_found(self):
        """
        Test that if GOV.UK Pay returns 404 when cancelling a payment, the method raises an HTTPError.
        """
        client = PaymentClient()

        payment_id = 'invalid'
        govuk_payment = {
            'payment_id': payment_id,
            'state': {
                'status': PaymentStatus.capturable.name,
            },
        }
        payment = {
            'uuid': 'b74a0eb6-0437-4b22-bce8-e6f11bd43802',
            'recipient_name': 'Alice Re',
            'prisoner_name': 'John Doe',
            'prisoner_number': 'AAB0A00',
            'amount': 1700,
        }
        with responses.RequestsMock() as rsps:
            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{payment_id}/cancel/'),
                status=404,
            )

            with self.assertRaises(HTTPError) as e:
                client.cancel_govuk_payment(payment, govuk_payment)

            self.assertEqual(
                e.exception.response.status_code,
                404,
            )

    def test_conflict(self):
        """
        Test that if GOV.UK Pay returns 409 when cancelling a payment, the method raises an HTTPError.
        """
        client = PaymentClient()

        payment_id = 'invalid'
        govuk_payment = {
            'payment_id': payment_id,
            'state': {
                'status': PaymentStatus.capturable.name,
            },
        }
        payment = {
            'uuid': 'b74a0eb6-0437-4b22-bce8-e6f11bd43802',
            'recipient_name': 'Alice Re',
            'prisoner_name': 'John Doe',
            'prisoner_number': 'AAB0A00',
            'amount': 1700,
        }
        with responses.RequestsMock() as rsps:
            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{payment_id}/cancel/'),
                status=409,
            )

            with self.assertRaises(HTTPError) as e:
                client.cancel_govuk_payment(payment, govuk_payment)

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
        - the method returns PaymentStatus.success
        - no email is sent
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
        with responses.RequestsMock() as rsps:
            mock_auth(rsps)

            # API call related to updating the email address on the payment record
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{payment["uuid"]}/'),
                status=200,
            )

            status = client.complete_payment_if_necessary(payment, govuk_payment)

        self.assertEqual(status, PaymentStatus.success)
        self.assertEqual(len(mail.outbox), 0)

    def test_capturable_payment_that_shouldnt_be_captured_yet(self):
        """
        Test that if the govuk payment is in 'capturable' state, the MTP payment record
        doesn't have the email field filled in and the payment should not be captured yet:

        - the MTP payment record is patched with the card details attributes
        - the method returns PaymentStatus.capturable
        - an email is sent to the sender
        """
        client = PaymentClient()

        payment = {
            'uuid': 'b74a0eb6-0437-4b22-bce8-e6f11bd43802',
            'recipient_name': 'Alice Re',
            'prisoner_name': 'John Doe',
            'prisoner_number': 'AAB0A00',
            'amount': 1700,
        }
        govuk_payment = {
            'payment_id': 'payment-id',
            'state': {
                'status': PaymentStatus.capturable.name,
            },
            'email': 'sender@example.com',
            'provider_id': '123456789',
            'card_details': {
                'cardholder_name': 'John Doe',
                'first_digits_card_number': '1234',
                'last_digits_card_number': '987',
                'expiry_date': '01/20',
                'card_brand': 'visa',
                'billing_address': 'Buckingham Palace SW1A 1AA',
            },
        }

        with \
                mock.patch.object(client, 'get_security_check_result', return_value=CheckResult.delay), \
                responses.RequestsMock() as rsps:

            mock_auth(rsps)

            # API call related to updating the email address and card details
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{payment["uuid"]}/'),
                status=200,
            )

            status = client.complete_payment_if_necessary(payment, govuk_payment)

            payment_patch_body = json.loads(rsps.calls[-1].request.body.decode())
            self.assertDictEqual(
                payment_patch_body,
                {
                    'email': 'sender@example.com',
                    'worldpay_id': '123456789',
                    'cardholder_name': 'John Doe',
                    'card_number_first_digits': '1234',
                    'card_number_last_digits': '987',
                    'card_expiry_date': '01/20',
                    'card_brand': 'visa',
                    'billing_address': 'Buckingham Palace SW1A 1AA',
                }
            )
        self.assertEqual(status, PaymentStatus.capturable)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(payment['email'], 'sender@example.com')
        self.assertEqual(mail.outbox[0].subject, 'Send money to someone in prison: your payment has been put on hold')

    def test_capturable_payment_that_shouldnt_be_captured_yet_with_email_already_set(self):
        """
        Test that if the govuk payment is in 'capturable' state, the MTP payment record
        has already the email field filled in and the payment should not be captured yet:

        - the method returns PaymentStatus.capturable
        - no email is sent as it
        """
        client = PaymentClient()

        payment = {
            'uuid': 'some-id',
            'email': 'some-sender@example.com',
            'worldpay_id': '123456789',
            'cardholder_name': 'John Doe',
            'card_number_first_digits': '1234',
            'card_number_last_digits': '987',
            'card_expiry_date': '01/20',
            'card_brand': 'visa',
            'billing_address': 'Buckingham Palace SW1A 1AA',
        }
        govuk_payment = {
            'payment_id': 'payment-id',
            'state': {
                'status': PaymentStatus.capturable.name,
            },
            'email': 'sender@example.com',
            'provider_id': '123456789',
            'card_details': {
                'cardholder_name': 'John Doe',
                'first_digits_card_number': '1234',
                'last_digits_card_number': '987',
                'expiry_date': '01/20',
                'card_brand': 'visa',
                'billing_address': 'Buckingham Palace SW1A 1AA',
            },
        }

        with mock.patch.object(client, 'get_security_check_result', return_value=CheckResult.delay):
            status = client.complete_payment_if_necessary(payment, govuk_payment)

        self.assertEqual(status, PaymentStatus.capturable)
        self.assertEqual(len(mail.outbox), 0)

    def test_capturable_payment_that_should_be_captured(self):
        """
        Test that if the govuk payment is in 'capturable' state and the payment should be captured:

        - the MTP payment record is patched with the card details attributes if necessary
        - the method captures the payment
        - the method returns PaymentStatus.success
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
            'provider_id': '123456789',
            'card_details': {
                'cardholder_name': 'John Doe',
                'first_digits_card_number': '1234',
                'last_digits_card_number': '987',
                'expiry_date': '01/20',
                'card_brand': 'visa',
                'billing_address': 'Buckingham Palace SW1A 1AA',
            },
        }

        with \
                mock.patch.object(client, 'get_security_check_result', return_value=CheckResult.capture), \
                responses.RequestsMock() as rsps:

            mock_auth(rsps)

            # API call related to updating the email address and card details
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{payment["uuid"]}/'),
                status=200,
            )

            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{govuk_payment["payment_id"]}/capture/'),
                status=204,
            )

            status = client.complete_payment_if_necessary(payment, govuk_payment)

            payment_patch_body = json.loads(rsps.calls[-2].request.body.decode())
            self.assertDictEqual(
                payment_patch_body,
                {
                    'email': 'sender@example.com',
                    'worldpay_id': '123456789',
                    'cardholder_name': 'John Doe',
                    'card_number_first_digits': '1234',
                    'card_number_last_digits': '987',
                    'card_expiry_date': '01/20',
                    'card_brand': 'visa',
                    'billing_address': 'Buckingham Palace SW1A 1AA',
                }
            )
        self.assertEqual(status, PaymentStatus.success)
        self.assertEqual(len(mail.outbox), 0)

    def test_capturable_payment_that_should_be_cancelled(self):
        """
        Test that if the govuk payment is in 'capturable' state and the payment should be cancelled:

        - the MTP payment record is patched with the card details attributes if necessary
        - the method cancels the payment
        - an email is sent
        - the method returns PaymentStatus.cancelled
        """
        client = PaymentClient()

        payment = {
            'uuid': 'some-id',
            'recipient_name': 'Alice Re',
            'prisoner_number': 'AAB0A00',
            'prisoner_name': 'John Doe',
            'amount': 1700,
        }
        govuk_payment = {
            'payment_id': 'payment-id',
            'state': {
                'status': PaymentStatus.capturable.name,
            },
            'email': 'sender@example.com',
            'provider_id': '123456789',
            'card_details': {
                'cardholder_name': 'John Doe',
                'first_digits_card_number': '1234',
                'last_digits_card_number': '987',
                'expiry_date': '01/20',
                'card_brand': 'visa',
                'billing_address': 'Buckingham Palace SW1A 1AA',
            },
        }

        with \
                mock.patch.object(client, 'get_security_check_result', return_value=CheckResult.cancel), \
                responses.RequestsMock() as rsps:

            mock_auth(rsps)

            # API call related to updating the email address and card details
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{payment["uuid"]}/'),
                status=200,
            )

            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{govuk_payment["payment_id"]}/cancel/'),
                status=204,
            )

            status = client.complete_payment_if_necessary(payment, govuk_payment)

            payment_patch_body = json.loads(rsps.calls[-2].request.body.decode())
            self.assertDictEqual(
                payment_patch_body,
                {
                    'email': 'sender@example.com',
                    'worldpay_id': '123456789',
                    'cardholder_name': 'John Doe',
                    'card_number_first_digits': '1234',
                    'card_number_last_digits': '987',
                    'card_expiry_date': '01/20',
                    'card_brand': 'visa',
                    'billing_address': 'Buckingham Palace SW1A 1AA',
                }
            )
        self.assertEqual(status, PaymentStatus.cancelled)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(payment['email'], 'sender@example.com')
        self.assertEqual(
            mail.outbox[0].subject,
            'Send money to someone in prison: your payment has NOT been sent to the prisoner',
        )

    def test_dont_send_email(self):
        """
        Test that the method only sends any email if the govuk payment status is 'capturable'
        and the MTP payment didn't have the email field set
        """
        client = PaymentClient()

        payment = {
            'uuid': 'some-id',
        }

        statuses = [
            status
            for status in PaymentStatus
            if status != PaymentStatus.capturable
        ]

        with responses.RequestsMock() as rsps, silence_logger():
            mock_auth(rsps)

            # API call related to updating the email address on the payment record
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
                actual_status = client.complete_payment_if_necessary(payment, govuk_payment)

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
        status = client.complete_payment_if_necessary(payment, govuk_payment)

        self.assertEqual(status, None)
        self.assertEqual(len(mail.outbox), 0)


class GetCompletionPaymentAttrUpdatesTestCase(SimpleTestCase):
    """
    Tests related to the get_completion_payment_attr_updates method
    """

    def test_with_none_govuk_payment(self):
        """
        Test that it returns {} if the passed in govuk payment is falsy.
        """
        client = PaymentClient()

        payment = {
            'worldpay_id': '123456789',
            'card_brand': 'visa',
        }
        govuk_payment = None
        attr_updates = client.get_completion_payment_attr_updates(payment, govuk_payment)

        self.assertEqual(attr_updates, {})

    def test_with_none_payment(self):
        """
        Test that it returns the non-falsy attrs in govuk_payment if the passed-in payment is falsy.
        """
        client = PaymentClient()

        payment = None
        govuk_payment = {
            'email': 'some@email.com',
            'provider_id': '',
            'card_details': {
                'cardholder_name': None,
                'card_brand': 'visa',
            },
            'extra_attribute': 'some-value',
        }
        attr_updates = client.get_completion_payment_attr_updates(payment, govuk_payment)

        self.assertEqual(
            attr_updates,
            {
                'email': 'some@email.com',
                'card_brand': 'visa',
            }
        )

    def test_get(self):
        """
        Test that the completion values in govuk_payment that are not already set in payment
        are returned.
        """
        client = PaymentClient()

        payment = {
            'email': 'existing@email.com',  # shouldn't get overridden
            'worldpay_id': '',  # should get updated
            'cardholder_name': None,  # should get updated
            'card_brand': 'visa',  # hasn't changed so should be ignored
        }
        govuk_payment = {
            'email': 'some@email.com',  # should be ignored
            'provider_id': '123456789',  # should be used
            'card_details': {
                'cardholder_name': 'John Doe',
                'first_digits_card_number': '1234',
                'last_digits_card_number': '987',
                'expiry_date': '01/20',
                'card_brand': 'visa',  # hasn't changed so should be ignored
                'billing_address': 'Buckingham Palace SW1A 1AA',
            },
            'extra_attribute': 'some-value',
        }
        attr_updates = client.get_completion_payment_attr_updates(payment, govuk_payment)

        self.assertEqual(
            attr_updates,
            {
                'worldpay_id': '123456789',
                'cardholder_name': 'John Doe',
                'card_number_first_digits': '1234',
                'card_number_last_digits': '987',
                'card_expiry_date': '01/20',
                'billing_address': 'Buckingham Palace SW1A 1AA',
            }
        )
