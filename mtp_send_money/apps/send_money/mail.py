from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext
from mtp_common.tasks import send_email

from send_money.utils import site_url


def _send_notification_email(email, template_name, subject, tags, context):
    context.update({
        'site_url': settings.START_PAGE_URL,
        'feedback_url': site_url(reverse('help_area:submit_ticket')),
        'help_url': site_url(reverse('help_area:help')),
    })
    send_email(
        email,
        f'send_money/email/{template_name}.txt',
        gettext('Send money to someone in prison: %(subject)s') % {'subject': subject},
        context=context,
        html_template=f'send_money/email/{template_name}.html',
        anymail_tags=tags,
    )


def _get_email_context_for_payment(payment):
    return {
        'short_payment_ref': payment['uuid'][:8].upper(),
        'prisoner_name': payment['recipient_name'],
        'prisoner_number': payment['prisoner_number'],
        'amount': Decimal(payment['amount']) / 100,
    }


def send_email_for_card_payment_confirmation(email, payment):
    context = _get_email_context_for_payment(payment)

    _send_notification_email(
        email,
        'debit-card-confirmation',
        gettext('your payment was successful'),
        ['dc-received'],
        context,
    )


def send_email_for_card_payment_on_hold(email, payment):
    context = _get_email_context_for_payment(payment)

    _send_notification_email(
        email,
        'debit-card-payment-on-hold',
        gettext('your payment has been put on hold'),
        ['dc-on-hold'],
        context,
    )


def send_email_for_card_payment_accepted(email, payment):
    context = _get_email_context_for_payment(payment)

    _send_notification_email(
        email,
        'debit-card-payment-accepted',
        gettext('your payment has now gone through'),
        ['dc-accepted'],
        context,
    )


def send_email_for_card_payment_rejected(email, payment):
    context = _get_email_context_for_payment(payment)
    context['compliance_contact'] = settings.COMPLIANCE_CONTACT_EMAIL or site_url(reverse('help_area:submit_ticket'))

    _send_notification_email(
        email,
        'debit-card-payment-rejected',
        gettext('your payment has NOT been sent to the prisoner'),
        ['dc-rejected'],
        context,
    )


def send_email_for_card_payment_timed_out(email, payment):
    context = _get_email_context_for_payment(payment)

    _send_notification_email(
        email,
        'debit-card-payment-timeout',
        gettext('payment session expired'),
        ['dc-timeout'],
        context,
    )


def send_email_for_bank_transfer_reference(email, context):
    _send_notification_email(
        email,
        'bank-transfer-reference',
        gettext('your prisoner reference is %(bank_transfer_reference)s') % context,
        ['bt-reference'],
        context,
    )
