from django import template
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

register = template.Library()

prison_name_prefixes = (
    ('HMP & YOI', _('Her Majesty’s Prison and Young Offender Institution')),
    ('HMP', _('Her Majesty’s Prison')),
    ('HMYOI & RC', _('Her Majesty’s Young Offender Institution and Remand Centre')),
    ('HMYOI', _('Her Majesty’s Young Offender Institution')),
    ('IRC', _('Immigration Removal Centre')),
)


@register.filter
def describe_abbreviation(prison_name):
    for prefix, description in prison_name_prefixes:
        if prison_name.startswith(prefix + ' '):
            prison_name = prison_name[len(prefix) + 1:]
            return format_html('<abbr title="{description}">{prefix}</abbr> {name}',
                               description=description, prefix=prefix, name=prison_name)
    return prison_name
