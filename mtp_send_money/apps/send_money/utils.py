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


def unserialise_date(date_text_day, date_text_month, date_text_year):
    date_text = force_text('%d-%02d-%d' % (date_text_year, date_text_month, date_text_month ))
    date = parse_date(date_text)
    if not date:
        raise ValueError('Invalid date')
    return date


def lenient_unserialise_date(date_text_day, date_text_month, date_text_year):
    date_text = force_text('%d-%02d-%d' % (date_text_year, date_text_month, date_text_month ))
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
    for link in data['links']:
        if link['rel'] == rel:
            return link
