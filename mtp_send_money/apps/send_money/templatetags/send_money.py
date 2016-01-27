from django import template
from django.forms.utils import flatatt

from send_money.models import PaymentMethod
from send_money.utils import format_percentage, \
    currency_format, currency_format_pence, get_total_charge

register = template.Library()


@register.filter
def payment_method_description(payment_method):
    return PaymentMethod.lookup_description(payment_method)


@register.filter(name='currency_format')
def currency_format_filter(amount):
    return currency_format(amount, trim_empty_pence=True)


@register.filter(name='currency_format_pence')
def currency_format_pence_filter(amount_pence):
    return currency_format_pence(amount_pence, trim_empty_pence=True)


@register.filter(name='format_percentage')
def format_percentage_filter(number):
    return format_percentage(number)


@register.filter
def add_service_charge(amount):
    return get_total_charge(amount)


@register.filter
def get_widget_attrs(bound_field, field_index=None):
    if field_index is not None:
        field = bound_field.field.fields[field_index]
    else:
        field = bound_field.field
    widget = field.widget
    attrs = widget.build_attrs()
    attrs.update(field.widget_attrs(widget))
    if hasattr(widget, 'input_type'):
        attrs['type'] = widget.input_type
    return flatatt(attrs)
