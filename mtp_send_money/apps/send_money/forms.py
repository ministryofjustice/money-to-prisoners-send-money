import decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from form_error_reporting import GARequestErrorReportingMixin
from requests.exceptions import RequestException
from slumber.exceptions import HttpNotFoundError, SlumberHttpBaseException

from send_money.fields import SplitDateField
from send_money.models import PaymentMethod
from send_money.utils import (
    serialise_date, unserialise_date, serialise_amount, unserialise_amount,
    validate_prisoner_number, get_api_client
)


class PrisonerDetailsForm(GARequestErrorReportingMixin, forms.Form):
    prisoner_number = forms.CharField(
        label=_('Prisoner number'),
        max_length=7,
        validators=[validate_prisoner_number],
    )
    prisoner_dob = SplitDateField(
        label=_('Prisoner date of birth'),
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
                    message=[_('No prisoner matches the details you’ve supplied.'),
                             _('Please contact the prisoner to check your details are correct.')],
                    code='not_found'
                )
        except (SlumberHttpBaseException, RequestException):
            raise ValidationError(
                message=[_('Could not connect to the service.'),
                         _('Please try again later.')],
                code='connection')
        return self.cleaned_data

    def save_form_data_in_session(self, session):
        session['prisoner_dob'] = serialise_date(self.cleaned_data['prisoner_dob'])
        session['prisoner_number'] = self.cleaned_data['prisoner_number']


class SendMoneyForm(PrisonerDetailsForm):
    field_order = ('prisoner_name', 'prisoner_dob', 'prisoner_number', 'amount')
    prisoner_name = forms.CharField(
        label=_('Prisoner name'),
        max_length=250,
    )
    amount = forms.DecimalField(
        label=_('Amount you are sending'),
        min_value=decimal.Decimal('0.01'),
        max_value=decimal.Decimal('1000000'),
        decimal_places=2,
    )
    payment_method = forms.ChoiceField(
        label=_('Payment method'),
        widget=forms.RadioSelect,
        choices=PaymentMethod.django_choices(),
        initial=PaymentMethod.debit_card,
    )
    email = forms.EmailField(
        label=_('Your email address'),
        required=False
    )

    def switch_to_hidden(self):
        for field in self.fields.values():
            field.widget = field.hidden_widget()

    def save_form_data_in_session(self, session):
        form_data = self.cleaned_data
        for field in self.get_field_names():
            session[field] = form_data[field]
        session['prisoner_dob'] = serialise_date(session['prisoner_dob'])
        session['amount'] = serialise_amount(session['amount'])

    @classmethod
    def form_data_from_session(cls, session):
        try:
            data = {
                field: session.get(field)
                for field in cls.get_field_names()
            }
            prisoner_dob = unserialise_date(data['prisoner_dob'])
            data['prisoner_dob'] = [prisoner_dob.day, prisoner_dob.month, prisoner_dob.year]
            data['amount'] = unserialise_amount(data['amount'])
            return data
        except (KeyError, ValueError):
            raise ValueError('Session does not have a valid form')
