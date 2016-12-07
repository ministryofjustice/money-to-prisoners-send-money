from django import forms
from django.utils.translation import gettext_lazy as _
from zendesk_tickets.forms import EmailTicketForm

from send_money.utils import validate_prisoner_number


class ContactForm(EmailTicketForm):
    ticket_content = forms.CharField(
        label=_('Enter the questions or feedback you have about this service'),
        widget=forms.Textarea,
    )
    prisoner_number = forms.CharField(
        label=_('Prisoner number'),
        help_text=_('Optional, for example: A1234BC'),
        max_length=7,
        validators=[validate_prisoner_number],
        required=False,
    )
    prisoner_dob = forms.CharField(
        label=_('Prisoner date of birth'),
        help_text=_('Optional, for example: 28/04/1996'),
        required=False,
    )
