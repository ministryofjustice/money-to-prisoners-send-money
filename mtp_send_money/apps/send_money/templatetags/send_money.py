from decimal import Decimal

from django import template

from send_money.forms import PaymentMethod
from send_money.utils import serialise_amount, unserialise_amount

register = template.Library()


@register.filter
def payment_method_description(payment_method):
    if not isinstance(payment_method, PaymentMethod):
        payment_method = PaymentMethod[payment_method]
    return payment_method.value


@register.filter
def currency_format(amount):
    """
    Formats a number into currency format
    @param amount: amount in pounds
    """
    if not isinstance(amount, Decimal):
        amount = unserialise_amount(amount)
    return '£' + serialise_amount(amount)


@register.filter
def currency_format_pence(amount_pence):
    """
    Formats a int into currency format
    @param amount_pence: amount in pence
    @type amount_pence: int
    """
    if amount_pence < 100:
        return '%sp' % amount_pence
    return currency_format(Decimal(amount_pence) / Decimal('100'))


@register.filter
def format_percentage(number):
    return '%s%%' % number
