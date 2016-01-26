from django import template

from send_money.models import PaymentMethod
from send_money.utils import format_percentage, \
    currency_format, currency_format_pence, get_total_charge

register = template.Library()


@register.filter
def payment_method_description(payment_method):
    return PaymentMethod.lookup_description(payment_method)


@register.filter(name='currency_format')
def currency_format_filter(amount):
    return currency_format(amount)


@register.filter(name='currency_format_pence')
def currency_format_pence_filter(amount_pence):
    return currency_format_pence(amount_pence)


@register.filter(name='format_percentage')
def format_percentage_filter(number):
    return format_percentage(number)


@register.filter
def add_service_charge(amount):
    return get_total_charge(amount)
