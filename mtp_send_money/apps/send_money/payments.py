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
from send_money.mail import (
    send_email_for_card_payment_accepted,
    send_email_for_card_payment_confirmation,
    send_email_for_card_payment_on_hold,
    send_email_for_card_payment_rejected,
    send_email_for_card_payment_timed_out,
)
from send_money.utils import (
    get_api_session,
    govuk_headers,
    govuk_url,
)

logger = logging.getLogger('mtp')


class GovUkPaymentStatus(enum.Enum):
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

    @classmethod
    def get_from_govuk_payment(cls, govuk_payment):
        """
        :return: GovUkPaymentStatus in the govuk_payment dict or None.

        :raise GovUkPaymentStatusException: if the input value is not in an expected format.
        """
        if not govuk_payment:
            return None

        try:
            return cls[
                govuk_payment['state']['status']
            ]
        except KeyError:
            raise GovUkPaymentStatusException(
                f"Unknown status: {govuk_payment.get('state', {}).get('status')}",
            )

    @classmethod
    def payment_timed_out_after_capturable(cls, govuk_payment):
        """
        :return: True if failed because of a timeout and the payment was in a capturable
            status at some point in the past.

        :raise GovUkPaymentStatusException: if the input value is not in the expected format.
        """
        status = cls.get_from_govuk_payment(govuk_payment)

        if status != cls.failed:
            return False

        error_code = govuk_payment['state'].get('code')
        if error_code != 'P0020':
            return False

        # check if there's a capturable event in the event log
        govuk_id = govuk_payment['payment_id']
        payment_client = PaymentClient()
        events = payment_client.get_govuk_payment_events(govuk_id)

        return any(
            event['state'].get('status') == cls.capturable.name
            for event in events
        )


class CheckResult(enum.Enum):
    """
    Maps the next action to perform based on the security check data.
    """
    delay = 'Delay'
    capture = 'Capture'
    cancel = 'Cancel'


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
    CHECK_INCOMPLETE_PAYMENT_DELAY = timedelta(minutes=30)

    @cached_property
    def api_session(self):
        return get_api_session()

    def create_payment(self, new_payment):
        api_response = self.api_session.post('/payments/', json=new_payment).json()
        return api_response['uuid']

    def get_incomplete_payments(self):
        older_than = timezone.now() - self.CHECK_INCOMPLETE_PAYMENT_DELAY
        return retrieve_all_pages_for_path(
            self.api_session, '/payments/', modified__lt=older_than.isoformat()
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

    def get_security_check_result(self, payment):
        """
        Checks the security check for 'payment' and returns a CheckResult indicating the next
        action to perform.
        """
        return CheckResult.capture

    def complete_payment_if_necessary(self, payment, govuk_payment):
        """
        Completes a payment if necessary and returns the resulting GovUkPaymentStatus.

        If the status is 'capturable' and the MTP payment doesn't have any email,
        it updates the email field on record and sends an email to the user.

        If the status is 'capturable' and the payment should be captured, this method
        captures the payment and returns the new status.

        If the status is 'capturable' and the payment should be cancelled, this method
        cancels the payment and returns the new status.

        :return: GovUkPaymentStatus for the GOV.UK payment govuk_payment
        :param payment: dict with MTP payment details as returned by the MTP API
        :param govuk_payment: dict with GOV.UK payment details as returned by the GOV.UK Pay API
        """
        govuk_status = GovUkPaymentStatus.get_from_govuk_payment(govuk_payment)
        if not govuk_status:
            return

        if govuk_status == GovUkPaymentStatus.error:
            logger.error(
                'GOV.UK Pay returned an error for %(govuk_id)s: %(code)s %(msg)s' %
                {
                    'govuk_id': govuk_payment['payment_id'],
                    'code': govuk_payment['state']['code'],
                    'msg': govuk_payment['state']['message'],
                },
            )

        successfulish = govuk_status in [GovUkPaymentStatus.success, GovUkPaymentStatus.capturable]
        # if nothing can be done, exist immediately
        if not successfulish:
            return govuk_status

        # update payment so that we can work out if it has to be delayed
        payment_attr_updates = self.get_completion_payment_attr_updates(payment, govuk_payment)
        if payment_attr_updates:
            self.update_payment(payment['uuid'], payment_attr_updates)
            payment.update(payment_attr_updates)

        if govuk_status == GovUkPaymentStatus.capturable:
            # decide next action
            check_action = self.get_security_check_result(payment)
            if check_action == CheckResult.delay:
                # if the user hasn't been notified, send email
                if 'email' in payment_attr_updates:
                    email = payment_attr_updates['email']
                    send_email_for_card_payment_on_hold(email, payment)
            elif check_action == CheckResult.capture:
                govuk_status = self.capture_govuk_payment(govuk_payment)
            elif check_action == CheckResult.cancel:
                govuk_status = self.cancel_govuk_payment(govuk_payment)

        return govuk_status

    def get_completion_payment_attr_updates(self, payment, govuk_payment):
        """
        Returns a dict of completion related attribute names and values extracted from govuk_payment
        that can be used to update payment.
        If an attribute is already set on payment or not set in govuk_payment, it will not be
        included in the returned value.
        """
        payment = payment or {}
        govuk_payment = govuk_payment or {}

        def get_attr(attr_name):
            def wrapper(govuk_payment):
                return govuk_payment.get(attr_name)
            return wrapper

        def get_card_details_attr_value(govuk_card_details_attr_name):
            def wrapper(govuk_payment):
                card_details = govuk_payment.get('card_details', {})
                return card_details.get(govuk_card_details_attr_name)
            return wrapper

        # (
        #   payment attribute name,
        #   callable to get the value from a govuk payment
        # )
        attrs_mapping = [
            ('email', get_attr('email')),
            ('worldpay_id', get_attr('provider_id')),
            ('cardholder_name', get_card_details_attr_value('cardholder_name')),
            ('card_number_first_digits', get_card_details_attr_value('first_digits_card_number')),
            ('card_number_last_digits', get_card_details_attr_value('last_digits_card_number')),
            ('card_expiry_date', get_card_details_attr_value('expiry_date')),
            ('card_brand', get_card_details_attr_value('card_brand')),
            ('billing_address', get_card_details_attr_value('billing_address')),
        ]

        attr_updates = {}
        for payment_attr_name, govuk_payment_attr_func in attrs_mapping:
            payment_attr_value = payment.get(payment_attr_name)
            if payment_attr_value:  # don't override existing values
                continue

            govuk_payment_attr_value = govuk_payment_attr_func(govuk_payment)

            # no value or hasn't changed
            if not govuk_payment_attr_value or govuk_payment_attr_value == payment_attr_value:
                continue

            attr_updates[payment_attr_name] = govuk_payment_attr_value

        return attr_updates

    def capture_govuk_payment(self, govuk_payment):
        """
        Captures and finalises a payment in status 'capturable'.

        :raise HTTPError: if GOV.UK Pay returns a 4xx or 5xx response
        """
        govuk_status = GovUkPaymentStatus.get_from_govuk_payment(govuk_payment)
        if govuk_status is None or govuk_status.finished():
            return govuk_status

        govuk_id = govuk_payment['payment_id']
        response = requests.post(
            govuk_url(f'/payments/{govuk_id}/capture'),
            headers=govuk_headers(),
            timeout=15,
        )

        response.raise_for_status()

        govuk_status = GovUkPaymentStatus.success
        govuk_payment['state']['status'] = govuk_status.name
        return govuk_status

    def cancel_govuk_payment(self, govuk_payment):
        """
        Cancels a payment in status 'capturable'.

        :raise HTTPError: if GOV.UK Pay returns a 4xx or 5xx response
        """
        govuk_status = GovUkPaymentStatus.get_from_govuk_payment(govuk_payment)
        if govuk_status is None or govuk_status.finished():
            return govuk_status

        govuk_id = govuk_payment['payment_id']
        response = requests.post(
            govuk_url(f'/payments/{govuk_id}/cancel'),
            headers=govuk_headers(),
            timeout=15,
        )

        response.raise_for_status()

        govuk_status = GovUkPaymentStatus.cancelled
        govuk_payment['state']['status'] = govuk_status.name
        return govuk_status

    def update_completed_payment(self, payment, govuk_payment):
        govuk_status = GovUkPaymentStatus.get_from_govuk_payment(govuk_payment)
        timed_out_after_capturable = GovUkPaymentStatus.payment_timed_out_after_capturable(govuk_payment)

        # update mtp payment
        payment_attr_updates = self.get_completion_payment_attr_updates({}, govuk_payment)

        if govuk_status == GovUkPaymentStatus.success:
            received_at = self.get_govuk_capture_time(govuk_payment)
            payment_attr_updates['received_at'] = received_at.isoformat()
            payment_attr_updates['status'] = 'taken'
        else:
            # TODO: we need a new mtp status for cancelled payments... 'cancelled'
            # TODO: if timed_out_after_capturable, failed payment and failed credit
            payment_attr_updates['status'] = 'failed'

        self.update_payment(payment['uuid'], payment_attr_updates)

        # send notification email
        email = (govuk_payment or {}).get('email')
        if not email:
            return

        if govuk_status == GovUkPaymentStatus.success:
            was_accepted_by_fiu = payment.get('security_check', {}).get('user_actioned')

            if was_accepted_by_fiu:
                send_email_for_card_payment_accepted(email, payment)
            else:
                send_email_for_card_payment_confirmation(email, payment)
        elif govuk_status == GovUkPaymentStatus.cancelled:
            send_email_for_card_payment_rejected(email, payment)
        elif govuk_status == GovUkPaymentStatus.failed:
            if timed_out_after_capturable:
                # it expired after being captured meaning that the user should really be notified
                security_check = payment.get('security_check', {})

                # if it was rejected by FIU, send rejection email anyway
                if security_check.get('user_actioned') and security_check.get('status') == 'rejected':
                    send_email_for_card_payment_rejected(email, payment)
                else:
                    send_email_for_card_payment_timed_out(email, payment)

                if not security_check.get('user_actioned'):
                    logger.warning(f'Payment {payment["uuid"]} timed out before being actioned by FIU')

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

    def get_govuk_payment_events(self, govuk_id):
        """
        :return: list with events information about a certain govuk payment.

        :param govuk_id: id of the govuk payment
        :raise HTTPError: if GOV.UK Pay returns a 4xx or 5xx response
        :raise RequestException: if the response body cannot be parsed
        """
        response = requests.get(
            govuk_url(f'/payments/{govuk_id}/events'),
            headers=govuk_headers(),
            timeout=15,
        )

        response.raise_for_status()

        try:
            data = response.json()
            return data['events']
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
            'Capture date not yet available for payment %s' % govuk_payment.get('reference')
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
