import decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from mtp_common.forms.fields import SplitDateField
from zendesk_tickets.forms import EmailTicketForm

from send_money.utils import RejectCardNumberValidator, validate_prisoner_number


class ContactForm(EmailTicketForm):
    ticket_content = forms.CharField(
        label=_('Enter your questions or feedback'),
        help_text=_('Don’t include card or bank details'),
        widget=forms.Textarea,
        validators=[RejectCardNumberValidator()],
    )
    contact_email = forms.EmailField(
        label=_('Your email address'),
        help_text=_('We need this so that we can send you a reply'),
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


class ContactNewPaymentForm(ContactForm):
    ticket_content = forms.CharField(
        label=_('Give details'),
        help_text=_('Don’t include card or bank details'),
        widget=forms.Textarea,
        validators=[RejectCardNumberValidator()],
    )
    prisoner_number = forms.CharField(
        label=_('Prisoner number'),
        help_text=_('For example, A1234BC'),
        max_length=7,
        validators=[validate_prisoner_number],
    )
    prisoner_dob = SplitDateField(
        label=_('Prisoner date of birth'),
        help_text=_('For example, 28 04 1996'),
    )
    contact_name = forms.CharField(
        label=_('Your name'),
        validators=[RejectCardNumberValidator()],
    )


class ContactSentPaymentForm(ContactNewPaymentForm):
    amount = forms.DecimalField(
        label=_('Payment amount'),
        min_value=decimal.Decimal('0.01'),
        decimal_places=2,
        error_messages={
            'invalid': _('Enter as a number'),
            'min_value': _('Amount should be 1p or more'),
            'max_decimal_places': _('Only use 2 decimal places'),
        }
    )
    payment_date = SplitDateField(
        label=_('Date of payment'),
        help_text=_('For example, 8 6 2020'),
    )

    def clean_payment_date(self):
        payment_date = self.cleaned_data.get('payment_date')
        if payment_date:
            today = timezone.now().date()
            if payment_date > today:
                self.add_error('payment_date', _('Date can’t be in the future'))
        return payment_date
