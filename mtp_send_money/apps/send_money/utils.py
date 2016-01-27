import datetime
from decimal import Decimal
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.dateformat import format as format_date
from django.utils.dateparse import parse_date
from django.utils import formats
from django.utils.encoding import force_text
from django.utils.translation import ugettext as _
from moj_auth import api_client, urljoin

prisoner_number_re = re.compile(r'^[a-z]\d\d\d\d[a-z]{2}$', re.IGNORECASE)


def get_api_client():
    return api_client.get_authenticated_connection(
        settings.SHARED_API_USERNAME,
        settings.SHARED_API_PASSWORD
    )


def validate_prisoner_number(value):
    if not prisoner_number_re.match(value):
        raise ValidationError(_('Incorrect prisoner number format'), code='invalid')


def format_percentage(number):
    return '%s%%' % number


def currency_format(amount, trim_empty_pence=False):
    """
    Formats a number into currency format
    @param amount: amount in pounds
    """
    if not isinstance(amount, Decimal):
        amount = unserialise_amount(amount)
    text_amount = serialise_amount(amount)
    if trim_empty_pence and text_amount.endswith('.00'):
        text_amount = text_amount[:-3]
    return '£' + text_amount


def currency_format_pence(amount_pence, trim_empty_pence=False):
    """
    Formats a int into currency format
    @param amount_pence: amount in pence
    @type amount_pence: int
    """
    if amount_pence < 100:
        return '%sp' % amount_pence
    return currency_format(Decimal(amount_pence) / Decimal('100'),
                           trim_empty_pence=trim_empty_pence)


def get_service_charge(amount):
    if not isinstance(amount, Decimal):
        amount = Decimal(amount)
    percentage_pence = amount * settings.SERVICE_CHARGE_PERCENTAGE
    fixed_pence = Decimal(settings.SERVICE_CHARGE_FIXED)
    return (percentage_pence + fixed_pence) / Decimal('100')


def get_total_charge(amount):
    if not isinstance(amount, Decimal):
        amount = Decimal(amount)
    return amount + get_service_charge(amount)


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
    return '%s %s' % (prisoner_number, format_date(prisoner_dob, 'd/m/Y'))


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
        return data['_links'][rel]
