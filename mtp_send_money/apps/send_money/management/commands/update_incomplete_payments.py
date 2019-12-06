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

logger = logging.getLogger('mtp')


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

    def perform_update(self):
        payment_client = PaymentClient()
        payments = payment_client.get_incomplete_payments()
        one_day_ago = timezone.now() - timedelta(days=1)
        for payment in payments:
            modified = parse_datetime(payment['modified'])
            if modified < one_day_ago:
                logger.warning(
                    'Payment %s was last modified at %s and is still pending' %
                    (payment['uuid'], modified.isoformat())
                )

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
                    'Scheduled job: Authentication error while processing %s' % payment_ref
                )
            except RequestException as error:
                error_message = 'Scheduled job: Payment check failed for ref %s' % payment_ref
                if hasattr(error, 'response') and hasattr(error.response, 'content'):
                    error_message += '\nReceived: %s' % error.response.content
                logger.exception(error_message)
            except GovUkPaymentStatusException:
                # expected much of the time
                pass
