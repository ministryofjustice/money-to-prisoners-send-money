import decimal

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
    if not isinstance(amount, decimal.Decimal):
        amount = unserialise_amount(amount)
    return '£' + serialise_amount(amount)
