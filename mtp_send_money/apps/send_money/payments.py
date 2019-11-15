import enum
from datetime import datetime, time, timedelta
import logging
from urllib.parse import quote_plus as url_quote

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from django.utils.functional import cached_property
from mtp_common.api import retrieve_all_pages_for_path
from mtp_common.auth.exceptions import HttpNotFoundError
import requests
from requests.exceptions import RequestException

from send_money.exceptions import GovUkPaymentStatusException
from send_money.utils import (
    get_api_session, govuk_headers, govuk_url, send_notification
)

logger = logging.getLogger('mtp')


class PaymentStatus(enum.Enum):
    created = 'Created',
    started = 'Started'
    submitted = 'Submitted'
    capturable = 'Capturable'  # in delayed capture
    success = 'Success'
    failed = 'Failed'
    cancelled = 'Cancelled'
    error = 'Error'

    def finished(self):
        return self in [self.success, self.failed, self.cancelled, self.error]

    def finished_and_failed(self):
        return self.finished() and self != self.success

    def is_awaiting_user_input(self):
        return self in [self.created, self.started, self.submitted]


def is_active_payment(payment):
    if payment['status'] == 'pending':
        return True

    date_str = payment.get('received_at')
    if date_str:
        received_at = parse_datetime(date_str)
        return (
            received_at is not None and
            (timezone.now() - received_at) < timedelta(minutes=settings.CONFIRMATION_EXPIRES)
        )
    else:
        return False


class PaymentClient:

    @cached_property
    def api_session(self):
        return get_api_session()

    def create_payment(self, new_payment):
        api_response = self.api_session.post('/payments/', json=new_payment).json()
        return api_response['uuid']

    def get_incomplete_payments(self):
        an_hour_ago = timezone.now() - timedelta(hours=1)
        return retrieve_all_pages_for_path(
            self.api_session, '/payments/', modified__lt=an_hour_ago.isoformat()
        )

    def get_payment(self, payment_ref):
        try:
            if payment_ref:
                return self.api_session.get('/payments/%s/' % url_quote(payment_ref)).json()
        except HttpNotFoundError:
            pass

    def update_payment(self, payment_ref, payment_update):
        if not payment_ref:
            raise ValueError('payment_ref must be provided')
        self.api_session.patch('/payments/%s/' % url_quote(payment_ref), json=payment_update)

    def parse_govuk_payment_status(self, govuk_payment):
        """
        :return: PaymentStatus in the govuk_payment dict.
        """
        if not govuk_payment:
            return None

        try:
            return PaymentStatus[
                govuk_payment['state']['status']
            ]
        except KeyError:
            raise GovUkPaymentStatusException(
                f"Unknown status: {govuk_payment['state']['status']}",
            )

    def should_be_automatically_captured(self, payment):
        # TODO: work out if payment needs to be delayed and and save result via API
        return True

    def complete_payment_if_necessary(self, payment, govuk_payment, context):
        """
        Completes a payment if necessary and returns the resulting PaymentStatus.

        If the status is 'success' or 'capturable' and the MTP payment doesn't have any email,
        it updates the email field on record and sends an email to the user.

        If the status is 'capturable' and the payment should be automatically captured, this method
        captures and returns the new status.

        If a payment is captured or it's found in success state for the first time, an email
        to the sender is sent.

        :return: PaymentStatus for the GOV.UK payment govuk_payment
        :param payment: dict with MTP payment details as returned by the MTP API
        :param govuk_payment: dict with GOV.UK payment details as returned by the GOV.UK Pay API
        :param context: dict with extra variable to be used in constructing any email message
        """
        govuk_status = self.parse_govuk_payment_status(govuk_payment)
        if not govuk_status:
            return

        if govuk_status == PaymentStatus.error:
            logger.error(
                'GOV.UK Pay returned an error for %(govuk_id)s: %(code)s %(msg)s' %
                {
                    'govuk_id': govuk_payment['payment_id'],
                    'code': govuk_payment['state']['code'],
                    'msg': govuk_payment['state']['message'],
                },
            )

        successfulish = govuk_status in [PaymentStatus.success, PaymentStatus.capturable]
        # if nothing can be done, exist immediately
        if not successfulish:
            return govuk_status

        email = govuk_payment.get('email')
        should_update_email = email and not payment.get('email')

        if govuk_status == PaymentStatus.success and should_update_email:
            # send successful email if it's the first time we get the sender's email address
            send_notification(email, context)
        elif govuk_status == PaymentStatus.capturable:
            if self.should_be_automatically_captured(payment):
                # capture payment and send successful email
                govuk_status = self.capture_payment(govuk_payment, context)

        # update email if necessary
        if should_update_email:
            self.update_payment(payment['uuid'], {'email': email})
            payment['email'] = email

        return govuk_status

    def capture_payment(self, govuk_payment, context):
        """
        Captures and finalises a payment in status 'capturable' and sends a confirmation email to the user.

        :raise HTTPError: if GOV.UK Pay returns a 4xx or 5xx response
        """
        govuk_status = self.parse_govuk_payment_status(govuk_payment)
        if govuk_status is None or govuk_status.finished():
            return govuk_status

        govuk_id = govuk_payment['payment_id']
        response = requests.post(
            govuk_url(f'/payments/{govuk_id}/capture'),
            headers=govuk_headers(),
            timeout=15,
        )

        response.raise_for_status()

        email = govuk_payment.get('email')
        send_notification(email, context)

        govuk_status = PaymentStatus.success
        govuk_payment['state']['status'] = govuk_status.name
        return govuk_status

    def update_completed_payment(self, payment_ref, govuk_payment, success):
        card_details = govuk_payment.get('card_details') if govuk_payment else None

        payment_update = {
            'status': 'taken' if success else 'failed'
        }
        if success:
            received_at = self.get_govuk_capture_time(govuk_payment)
            payment_update['received_at'] = received_at.isoformat()
        if govuk_payment and govuk_payment.get('provider_id'):
            payment_update['worldpay_id'] = govuk_payment['provider_id']
        if card_details:
            if 'cardholder_name' in card_details:
                payment_update['cardholder_name'] = card_details['cardholder_name']
            if 'first_digits_card_number' in card_details:
                payment_update['card_number_first_digits'] = card_details['first_digits_card_number']
            if 'last_digits_card_number' in card_details:
                payment_update['card_number_last_digits'] = card_details['last_digits_card_number']
            if 'expiry_date' in card_details:
                payment_update['card_expiry_date'] = card_details['expiry_date']
            if 'card_brand' in card_details:
                payment_update['card_brand'] = card_details['card_brand']
            if card_details.get('billing_address'):
                payment_update['billing_address'] = card_details['billing_address']
        self.update_payment(payment_ref, payment_update)

    def get_govuk_payment(self, govuk_id):
        response = requests.get(
            govuk_url('/payments/%s' % govuk_id),
            headers=govuk_headers(),
            timeout=15
        )

        if response.status_code != 200:
            if response.status_code == 404:
                return None
            raise RequestException(
                'Unexpected status code: %s' % response.status_code,
                response=response
            )
        try:
            data = response.json()
            try:
                validate_email(data.get('email'))
            except ValidationError:
                data['email'] = None
            return data
        except (ValueError, KeyError):
            raise RequestException('Cannot parse response', response=response)

    def get_govuk_capture_time(self, govuk_payment):
        try:
            capture_submit_time = parse_datetime(
                govuk_payment['settlement_summary'].get('capture_submit_time', '')
            )
            captured_date = parse_date(
                govuk_payment['settlement_summary'].get('captured_date', '')
            )
            if captured_date is not None:
                capture_submit_time = (
                    capture_submit_time or timezone.now()
                ).astimezone(timezone.utc)
                if capture_submit_time.date() < captured_date:
                    return datetime.combine(
                        captured_date, time.min
                    ).replace(tzinfo=timezone.utc)
                elif capture_submit_time.date() > captured_date:
                    return datetime.combine(
                        captured_date, time.max
                    ).replace(tzinfo=timezone.utc)
                else:
                    return capture_submit_time
        except (KeyError, TypeError):
            pass
        raise GovUkPaymentStatusException(
            'Capture date not yet available for payment %s' % govuk_payment['reference']
        )

    def create_govuk_payment(self, payment_ref, new_govuk_payment):
        govuk_response = requests.post(
            govuk_url('/payments'), headers=govuk_headers(),
            json=new_govuk_payment, timeout=15
        )

        try:
            if govuk_response.status_code != 201:
                raise ValueError('Status code not 201')
            govuk_data = govuk_response.json()
            payment_update = {
                'processor_id': govuk_data['payment_id']
            }
            self.update_payment(payment_ref, payment_update)
            return govuk_data
        except (KeyError, ValueError):
            logger.exception(
                'Failed to create new GOV.UK payment for MTP payment %s. Received: %s'
                % (payment_ref, govuk_response.content)
            )
