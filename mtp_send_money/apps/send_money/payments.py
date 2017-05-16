from datetime import datetime, time, timedelta
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from django.utils.functional import cached_property
from mtp_common.api import retrieve_all_pages
import requests
from requests.exceptions import RequestException

from send_money.exceptions import GovUkPaymentStatusException
from send_money.utils import (
    get_api_client, govuk_headers, govuk_url, send_notification
)

logger = logging.getLogger('mtp')


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
    def client(self):
        return get_api_client()

    def create_payment(self, new_payment):
        api_response = self.client.payments.post(new_payment)
        return api_response['uuid']

    def get_incomplete_payments(self):
        an_hour_ago = timezone.now() - timedelta(hours=1)
        return retrieve_all_pages(
            self.client.payments.get, modified__lt=an_hour_ago.isoformat()
        )

    def get_payment(self, payment_ref):
        from slumber.exceptions import HttpNotFoundError
        try:
            if payment_ref:
                return self.client.payments(payment_ref).get()
        except HttpNotFoundError:
            pass

    def update_payment(self, payment_ref, payment_update):
        if not payment_ref:
            raise ValueError('payment_ref must be provided')
        self.client.payments(payment_ref).patch(payment_update)

    def check_govuk_payment_succeeded(self, payment, govuk_payment, context):
        if govuk_payment is None:
            return False

        govuk_status = govuk_payment['state']['status']
        email = govuk_payment.get('email')

        if govuk_status not in ('success', 'error', 'cancelled', 'failed'):
            raise GovUkPaymentStatusException('Incomplete status: %s' % govuk_status)

        if govuk_status == 'error':
            logger.error(
                'GOV.UK Pay returned an error for %(govuk_id)s: %(code)s %(msg)s' %
                {'govuk_id': govuk_payment['payment_id'],
                 'code': govuk_payment['state']['code'],
                 'msg': govuk_payment['state']['message']}
            )
        success = govuk_status == 'success'

        if success and email and not payment.get('email'):
            context['nomis_integration_available'] = self.is_nomis_integration_available(payment)
            send_notification(email, context)
            self.update_payment(payment['uuid'], {'email': email})

        return success

    def update_completed_payment(self, payment_ref, govuk_payment, success):
        card_details = govuk_payment.get('card_details') if govuk_payment else None

        payment_update = {
            'status': 'taken' if success else 'failed'
        }
        if success:
            received_at = self.get_govuk_capture_time(govuk_payment)
            payment_update['received_at'] = received_at.isoformat()
        if card_details:
            if 'cardholder_name' in card_details:
                payment_update['cardholder_name'] = card_details['cardholder_name']
            if 'last_digits_card_number' in card_details:
                payment_update['card_number_last_digits'] = card_details['last_digits_card_number']
            if 'expiry_date' in card_details:
                payment_update['card_expiry_date'] = card_details['expiry_date']
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

    def is_nomis_integration_available(self, payment):
        data = self.client.prisoner_validity().get(
            prisoner_number=payment['prisoner_number'],
            prisoner_dob=payment['prisoner_dob']
        )
        return len(data['results']) > 0 and data['results'][0].get('nomis_integrated_prison', False)
