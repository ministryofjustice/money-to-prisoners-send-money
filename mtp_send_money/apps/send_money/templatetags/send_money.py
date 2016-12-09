import datetime

from django import template

from send_money.utils import (
    format_percentage, currency_format, currency_format_pence, get_total_charge
)

register = template.Library()


@register.filter(name='currency_format')
def currency_format_filter(amount, trim_empty_pence=True):
    return currency_format(amount, trim_empty_pence=trim_empty_pence)


@register.filter(name='currency_format_pence')
def currency_format_pence_filter(amount, trim_empty_pence=True):
    return currency_format_pence(amount, trim_empty_pence=trim_empty_pence)


@register.filter(name='format_percentage')
def format_percentage_filter(number, decimals=1):
    return format_percentage(number, decimals=decimals)


@register.filter
def add_service_charge(amount):
    return get_total_charge(amount)


@register.filter
def prepare_prisoner_dob(dob):
    if isinstance(dob, (list, tuple)):
        try:
            dob = datetime.date(int(dob[2]), int(dob[1]), int(dob[0]))
        except (ValueError, IndexError):
            return None
    if not isinstance(dob, datetime.date):
        return None
    return dob


@register.filter
def prisoner_details_not_found(error_list):
    return any(error.code == 'not_found' for error in error_list.as_data())
