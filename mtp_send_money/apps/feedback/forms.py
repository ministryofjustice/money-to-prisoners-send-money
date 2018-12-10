from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from zendesk_tickets.forms import EmailTicketForm

from send_money.utils import RejectCardNumberValidator, validate_prisoner_number


class ContactForm(EmailTicketForm):
    ticket_content = forms.CharField(
        label=_('Enter questions or feedback about this service'),
        help_text=_('Don’t include bank details or other personal information'),
        widget=forms.Textarea,
        validators=[RejectCardNumberValidator()],
    )
    prisoner_number = forms.CharField(
        label=_('Prisoner number'),
        help_text=_('For example, A1234BC'),
        max_length=7,
        validators=[validate_prisoner_number],
        required=False,
    )
    prisoner_dob = forms.CharField(
        label=_('Prisoner date of birth'),
        help_text=_('For example, 28/04/1996'),
        required=False,
        validators=[RejectCardNumberValidator()],
    )
    contact_email = forms.EmailField(
        label=_('Enter your email address if you’d like a reply'),
        help_text=_('We won’t use it for anything else'),
        required=False
    )
    # `subject` is a hidden honeypot field to try and lessen bot spam
    subject = forms.CharField(
        label='What is the subject of your enquiry?',
        required=False,
    )

    def clean(self):
        if self.cleaned_data['subject']:
            raise ValidationError(_('The service is currently unavailable'))
        return self.cleaned_data
