import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_UP
import logging
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.utils.dateformat import format as format_date
from django.utils.dateparse import parse_date
from django.utils import formats
from django.utils.encoding import force_text
from django.utils.translation import gettext, gettext_lazy as _
from mtp_common.auth import api_client, urljoin
from mtp_common.email import send_email
import requests
from requests.exceptions import Timeout

logger = logging.getLogger('mtp')
prisoner_number_re = re.compile(r'^[a-z]\d\d\d\d[a-z]{2}$', re.IGNORECASE)


def get_api_client():
    return api_client.get_authenticated_connection(
        settings.SHARED_API_USERNAME,
        settings.SHARED_API_PASSWORD
    )


def check_payment_service_available():
    try:
        response = requests.get('%s/healthcheck.json' % settings.API_URL, timeout=5)
        if response.status_code == 500:
            gov_uk_status = response.json().get('gov_uk_pay')
            return gov_uk_status is None or gov_uk_status.get('status', True)
    except Timeout:
        pass
    return True


def send_notification(email, context):
    from smtplib import SMTPException
    if not email:
        return False
    context.update({
        'site_url': settings.START_PAGE_URL,
        'feedback_url': site_url(reverse('submit_ticket')),
        'help_url': site_url(reverse('send_money:help')),
    })
    try:
        send_email(
            email, 'send_money/email/debit-card-confirmation.txt',
            gettext('Send money to a prisoner: your payment was successful'),
            context=context, html_template='send_money/email/debit-card-confirmation.html'
        )
        return True
    except SMTPException:
        logger.exception('Could not send successful payment notification')


def validate_prisoner_number(value):
    if not prisoner_number_re.match(value):
        raise ValidationError(_('Incorrect prisoner number format'), code='invalid')


def format_percentage(number, decimals=1, trim_zeros=True):
    if not isinstance(number, Decimal):
        number = Decimal(number)
    percentage_text = ('{0:.%sf}' % decimals).format(number)
    if decimals and trim_zeros and percentage_text.endswith('.' + ('0' * decimals)):
        percentage_text = percentage_text[:-decimals - 1]
    return percentage_text + '%'


def currency_format(amount, trim_empty_pence=False):
    """
    Formats a number into currency format
    @param amount: amount in pounds
    @param trim_empty_pence: if True, strip off .00
    """
    if not isinstance(amount, Decimal):
        amount = unserialise_amount(amount)
    text_amount = serialise_amount(amount)
    if trim_empty_pence and text_amount.endswith('.00'):
        text_amount = text_amount[:-3]
    return '£' + text_amount


def currency_format_pence(amount, trim_empty_pence=False):
    """
    Formats a number into currency format display pence only as #p
    @param amount: amount in pounds
    @param trim_empty_pence: if True, strip off .00
    """
    if not isinstance(amount, Decimal):
        amount = unserialise_amount(amount)
    if amount.__abs__() < Decimal('1'):
        return '%sp' % (amount * Decimal('100')).to_integral_value()
    return currency_format(amount, trim_empty_pence=trim_empty_pence)


def clamp_amount(amount):
    """
    Round the amount to integer pence,
    rounding fractional pence up (away from zero) for any fractional pence value
    that is greater than or equal to a tenth of a penny.
    @param amount: Decimal amount to round
    """
    tenths_of_pennies = (amount * Decimal('1000')).to_integral_value(rounding=ROUND_DOWN)
    pounds = tenths_of_pennies / Decimal('1000')
    return pounds.quantize(Decimal('1.00'), rounding=ROUND_UP)


def get_service_charge(amount, clamp=True):
    if not isinstance(amount, Decimal):
        amount = Decimal(amount)
    percentage_charge = amount * settings.SERVICE_CHARGE_PERCENTAGE / Decimal('100')
    service_charge = percentage_charge + settings.SERVICE_CHARGE_FIXED
    if clamp:
        return clamp_amount(service_charge)
    return service_charge


def get_total_charge(amount, clamp=True):
    if not isinstance(amount, Decimal):
        amount = Decimal(amount)
    charge = get_service_charge(amount, clamp=False)
    result = amount + charge
    if clamp:
        return clamp_amount(result)
    return result


def serialise_amount(amount):
    return '{0:.2f}'.format(amount)


def unserialise_amount(amount_text):
    amount_text = force_text(amount_text)
    return Decimal(amount_text)


def serialise_date(date):
    return format_date(date, 'Y-m-d')


def unserialise_date(date_text):
    date_text = force_text(date_text)
    date = parse_date(date_text)
    if not date:
        raise ValueError('Invalid date')
    return date


def lenient_unserialise_date(date_text):
    date_text = force_text(date_text)
    date_formats = formats.get_format('DATE_INPUT_FORMATS')
    for date_format in date_formats:
        try:
            return datetime.datetime.strptime(date_text, date_format).date()
        except (ValueError, TypeError):
            continue
    raise ValueError('Invalid date')


def bank_transfer_reference(prisoner_number, prisoner_dob):
    return '%s/%s' % (prisoner_number, format_date(prisoner_dob, 'd/m/Y'))


def govuk_headers():
    return {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': 'Bearer %s' % settings.GOVUK_PAY_AUTH_TOKEN
    }


def govuk_url(path):
    return urljoin(settings.GOVUK_PAY_URL, path)


def api_url(path):
    return urljoin(settings.API_URL, path)


def site_url(path):
    return urljoin(settings.SITE_URL, path)


def get_link_by_rel(data, rel):
    if rel in data['_links']:
        return data['_links'][rel]['href']
