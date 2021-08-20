from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from mtp_common.tasks import send_email

from send_money.notify.templates import SendMoneyNotifyTemplates
from send_money.utils import currency_format, site_url


def _send_notification_email(email, payment, template_name, reference_prefix):
    personalisation = {
        'site_url': settings.START_PAGE_URL,
        'help_url': site_url(reverse('help_area:help')),
        'compliance_contact': settings.COMPLIANCE_CONTACT_EMAIL or site_url(reverse('help_area:help')),
        'today': timezone.localdate().strftime('%d/%m/%Y'),

        'short_payment_ref': payment['uuid'][:8].upper(),
        'prisoner_name': payment['recipient_name'],
        'prisoner_number': payment['prisoner_number'],
        'amount': currency_format(Decimal(payment['amount']) / 100),
    }
    personalisation = {
        field: personalisation[field]
        for field in SendMoneyNotifyTemplates.templates[template_name]['personalisation']
    }
    send_email(
        template_name=template_name,
        to=email,
        personalisation=personalisation,
        reference='%s-%s' % (reference_prefix, payment['uuid']),
        staff_email=False,
    )


def send_email_for_card_payment_confirmation(email, payment):
    _send_notification_email(email, payment, 'send-money-debit-card-confirmation', 'confirmation')


def send_email_for_card_payment_on_hold(email, payment):
    _send_notification_email(email, payment, 'send-money-debit-card-payment-on-hold', 'on-hold')


def send_email_for_card_payment_accepted(email, payment):
    _send_notification_email(email, payment, 'send-money-debit-card-payment-accepted', 'accepted')


def send_email_for_card_payment_rejected(email, payment):
    _send_notification_email(email, payment, 'send-money-debit-card-payment-rejected', 'rejected')


def send_email_for_card_payment_timed_out(email, payment):
    _send_notification_email(email, payment, 'send-money-debit-card-payment-timeout', 'timeout')
