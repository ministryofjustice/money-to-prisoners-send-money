from datetime import timedelta
import logging

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.functional import cached_property
from mtp_common.api import retrieve_all_pages
import requests
from requests.exceptions import RequestException

from send_money.exceptions import GovUkPaymentStatusException
from send_money.utils import (
    get_api_client, govuk_headers, govuk_url, send_notification, get_link_by_rel
)

logger = logging.getLogger('mtp')


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

    def check_govuk_payment_status(self, payment_ref, govuk_id, context):
        govuk_payment = self.get_govuk_payment(govuk_id)
        govuk_status = govuk_payment['state']['status']
        email = govuk_payment['email']

        if govuk_status not in ('success', 'error', 'cancelled', 'failed'):
            raise GovUkPaymentStatusException('Incomplete status: %s' % govuk_status)

        if govuk_status == 'error':
            logger.error('GOV.UK Pay returned an error: %(code)s %(msg)s' %
                         {'code': govuk_payment['state']['code'],
                          'msg': govuk_payment['state']['message']})
        success = govuk_status == 'success'

        payment_update = {
            'status': 'taken' if success else 'failed'
        }
        if success:
            received_at = self.get_govuk_capture_time(govuk_payment)
            if received_at is not None:
                payment_update['received_at'] = received_at.isoformat()
        if email:
            payment_update['email'] = email
        self.update_payment(payment_ref, payment_update)

        if success:
            # notify sender if email known, but still show success page if it fails
            context['email_sent'] = send_notification(email, context)

        return (success, context)

    def get_govuk_payment(self, govuk_id):
        response = requests.get(
            govuk_url('/payments/%s' % govuk_id),
            headers=govuk_headers(),
            timeout=15
        )
        if response.status_code != 200:
            raise RequestException('Status code not 200', response=response)
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
        response = requests.get(
            get_link_by_rel(govuk_payment, 'events'),
            headers=govuk_headers(),
            timeout=15
        )

        if response.status_code != 200:
            raise RequestException('Status code not 200', response=response)
        try:
            data = response.json()
            for event in data['events']:
                if event['state']['status'] == 'success':
                    return parse_datetime(event['updated'])
        except (ValueError, KeyError):
            raise RequestException('Cannot parse response', response=response)

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