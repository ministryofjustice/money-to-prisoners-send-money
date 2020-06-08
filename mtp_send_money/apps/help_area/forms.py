import decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
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
    prisoner_dob = forms.CharField(
        label=_('Prisoner date of birth'),
        help_text=_('For example, 28/04/1996'),
        validators=[RejectCardNumberValidator()],
    )
    contact_name = forms.CharField(
        label=_('Your name'),
        validators=[RejectCardNumberValidator()],
    )
    payment_method = forms.ChoiceField(
        label=_('Type of payment'),
        choices=(
            ('debit_card', _('Debit card')),
            ('bank_transfer', _('Bank transfer')),
        ),
    )

    def clean_payment_method(self):
        payment_method = self.cleaned_data.get('payment_method')
        if payment_method:
            for value, name in self.fields['payment_method'].choices:
                if value == payment_method:
                    self.cleaned_data['payment_method_name'] = name
                    break
        return payment_method


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
    payment_date = forms.CharField(
        label=_('Date of payment'),
        help_text=_('For example, 28/04/2020'),
        validators=[RejectCardNumberValidator()],
    )
