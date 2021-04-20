from datetime import timedelta
import logging

from django.core.management import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from mtp_common.stack import StackException, is_first_instance
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException

from send_money.exceptions import GovUkPaymentStatusException
from send_money.payments import GovUkPaymentStatus, PaymentClient
from send_money.views import get_payment_delayed_capture_rollout_percentage

logger = logging.getLogger('mtp')


ALWAYS_CHECK_IF_OLDER_THAN = timedelta(days=3)


class Command(BaseCommand):
    def handle(self, **options):
        verbosity = options['verbosity']
        if self.should_perform_update():
            if verbosity:
                self.stdout.write('Updating incomplete payments')
            self.perform_update()
        elif verbosity:
            self.stdout.write('Not updating incomplete payments because running on secondary instance')

    def should_perform_update(self):
        try:
            return is_first_instance()
        except StackException:
            self.stderr.write('Not running on Cloud Platform')
            return True

    def should_be_checked(self, payment):
        """
        Returns True if the GOV.UK Pay API should be used to check the status of the payment.

        Used to limit the amount of API calls to GOV.UK Pay endpoints.
        """
        # if delayed capture hasn't been released yet => always check
        if not get_payment_delayed_capture_rollout_percentage():
            return True

        creation_date = parse_datetime(payment['created'])
        security_check = payment.get('security_check')
        is_old = creation_date < (timezone.now() - ALWAYS_CHECK_IF_OLDER_THAN)

        if not security_check or is_old:
            return True

        return security_check.get('status') != 'pending'

    def perform_update(self):
        payment_client = PaymentClient()
        payments = payment_client.get_incomplete_payments()
        for payment in payments:
            if not self.should_be_checked(payment):
                continue

            payment_ref = payment['uuid']
            govuk_id = payment['processor_id']

            try:
                govuk_payment = payment_client.get_govuk_payment(govuk_id)
                previous_govuk_status = GovUkPaymentStatus.get_from_govuk_payment(govuk_payment)
                govuk_status = payment_client.complete_payment_if_necessary(payment, govuk_payment)

                # not yet finished and can't do anything so skip
                if govuk_status and not govuk_status.finished():
                    continue

                if previous_govuk_status != govuk_status:
                    # refresh govuk payment to get up-to-date fields (e.g. error codes)
                    govuk_payment = payment_client.get_govuk_payment(govuk_id)

                # if here, status is either success, failed, cancelled, error
                # or None (in case of govuk payment not found)
                payment_client.update_completed_payment(payment, govuk_payment)
            except OAuth2Error:
                logger.exception(
                    'Scheduled job: Authentication error while processing %(payment_ref)s',
                    {'payment_ref': payment_ref},
                )
            except RequestException as error:
                response_content = None
                if hasattr(error, 'response') and hasattr(error.response, 'content'):
                    response_content = error.response.content
                logger.exception(
                    'Scheduled job: Payment check failed for ref %(payment_ref)s. Received: %(response_content)s',
                    {'payment_ref': payment_ref, 'response_content': response_content},
                )
            except GovUkPaymentStatusException:
                # expected much of the time
                pass
