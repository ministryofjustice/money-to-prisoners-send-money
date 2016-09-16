import decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from form_error_reporting import GARequestErrorReportingMixin
from mtp_common.forms.fields import SplitDateField
from requests.exceptions import RequestException
from slumber.exceptions import HttpNotFoundError, SlumberHttpBaseException

from send_money.models import PaymentMethod
from send_money.utils import (
    serialise_date, unserialise_date, serialise_amount, unserialise_amount,
    validate_prisoner_number, get_api_client
)


class PaymentMethodForm(GARequestErrorReportingMixin, forms.Form):
    payment_method = forms.ChoiceField(error_messages={
        'required': _('Please choose how you want to send money')
    }, choices=PaymentMethod.django_choices())

    def __init__(self, show_bank_transfer_first, **kwargs):
        super().__init__(**kwargs)
        if show_bank_transfer_first:
            self['payment_method'].field.choices = reversed(self['payment_method'].field.choices)

    @property
    def chosen_view_name(self):
        if self.cleaned_data['payment_method'] == PaymentMethod.bank_transfer.name:
            return 'send_money:prisoner_details_bank'
        return 'send_money:prisoner_details_debit'


class PrisonerDetailsForm(GARequestErrorReportingMixin, forms.Form):
    prisoner_number = forms.CharField(
        label=_('Prisoner number'),
        help_text=_('eg A1234BC'),
        max_length=7,
        validators=[validate_prisoner_number],
    )
    prisoner_dob = SplitDateField(
        label=_('Prisoner date of birth'),
        help_text=_('eg 28 04 1996'),
    )

    @classmethod
    def get_field_names(cls):
        return [field for field in cls.base_fields]

    @classmethod
    def get_required_field_names(cls):
        return [name for name, field in cls.base_fields.items() if field.required]

    @classmethod
    def session_contains_form_data(cls, session):
        for required_key in cls.get_required_field_names():
            if not session.get(required_key):
                return False
        return True

    def __init__(self, request, **kwargs):
        self.request = request
        super().__init__(**kwargs)

    def clean_prisoner_number(self):
        prisoner_number = self.cleaned_data.get('prisoner_number')
        if prisoner_number:
            prisoner_number = prisoner_number.upper()
        return prisoner_number

    def check_prisoner_validity(self, prisoner_number, prisoner_dob):
        prisoner_dob = serialise_date(prisoner_dob)
        client = get_api_client()
        try:
            prisoners = client.prisoner_validity().get(prisoner_number=prisoner_number,
                                                       prisoner_dob=prisoner_dob)
            assert prisoners['count'] == 1
            prisoner = prisoners['results'][0]
            return prisoner and prisoner['prisoner_number'] == prisoner_number \
                and prisoner['prisoner_dob'] == prisoner_dob
        except (HttpNotFoundError, KeyError, IndexError, AssertionError):
            pass
        return False

    def clean(self):
        prisoner_number = self.cleaned_data.get('prisoner_number')
        prisoner_dob = self.cleaned_data.get('prisoner_dob')
        try:
            if not self.errors and \
                    not self.check_prisoner_validity(prisoner_number, prisoner_dob):
                raise ValidationError(
                    message=[_('No prisoner matches the details you’ve supplied, '
                               'please ask the prisoner to check your details are correct')],
                    code='not_found'
                )
        except (SlumberHttpBaseException, RequestException):
            raise ValidationError(
                message=[_('This service is currently unavailable')],
                code='connection')
        return self.cleaned_data

    def save_form_data_in_session(self, session):
        session['prisoner_dob'] = serialise_date(self.cleaned_data['prisoner_dob'])
        session['prisoner_number'] = self.cleaned_data['prisoner_number']


class StartPaymentPrisonerDetailsForm(PrisonerDetailsForm):
    field_order = ('prisoner_name', 'prisoner_dob', 'prisoner_number',)
    prisoner_name = forms.CharField(
        label=_('Prisoner name'),
        max_length=250,
    )

    def save_form_data_in_session(self, session):
        form_data = self.cleaned_data
        for field in self.get_field_names():
            session[field] = form_data[field]
        session['prisoner_dob'] = serialise_date(session['prisoner_dob'])

    @classmethod
    def form_data_from_session(cls, session):
        try:
            data = {
                field: session.get(field)
                for field in cls.get_field_names()
            }
            prisoner_dob = unserialise_date(data['prisoner_dob'])
            data['prisoner_dob'] = [prisoner_dob.day, prisoner_dob.month, prisoner_dob.year]
            return data
        except (KeyError, ValueError):
            raise ValueError('Session does not have a valid form')


class SendMoneyForm(StartPaymentPrisonerDetailsForm):
    visible_fields = ('amount',)
    amount = forms.DecimalField(
        label=_('Amount you are sending'),
        min_value=decimal.Decimal('0.01'),
        max_value=decimal.Decimal('1000000'),
        decimal_places=2,
        error_messages={
            'invalid': _('Enter as a number'),
            'min_value': _('Amount should be 1p or more'),
            'max_decimal_places': _('Only use 2 decimal places'),
        }
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in self.visible_fields:
                field.widget = field.hidden_widget()

    def switch_to_hidden(self):
        for field in self.fields.values():
            field.widget = field.hidden_widget()

    def save_form_data_in_session(self, session):
        super().save_form_data_in_session(session)
        session['amount'] = serialise_amount(session['amount'])

    @classmethod
    def form_data_from_session(cls, session):
        data = super().form_data_from_session(session)
        data['amount'] = unserialise_amount(data['amount'])
        return data
