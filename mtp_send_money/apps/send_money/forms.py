import datetime
import decimal
import logging
import threading

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from form_error_reporting import GARequestErrorReportingMixin
from mtp_common.forms.fields import SplitDateField
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException
from slumber.exceptions import HttpClientError, HttpNotFoundError, SlumberHttpBaseException

from send_money.models import PaymentMethod
from send_money.utils import (
    serialise_amount, unserialise_amount, serialise_date, unserialise_date,
    get_api_client, validate_prisoner_number, check_payment_service_available
)

logger = logging.getLogger('mtp')


class SendMoneyForm(GARequestErrorReportingMixin, forms.Form):
    @classmethod
    def unserialise_from_session(cls, request):
        session = request.session

        def get_value(f):
            value = session.get(f)
            if hasattr(cls, 'unserialise_%s' % f) and value is not None:
                value = getattr(cls, 'unserialise_%s' % f)(value)
            return value

        return cls(data={
            field: get_value(field)
            for field in cls.base_fields
        })

    def serialise_to_session(self, request):
        cls = self.__class__
        session = request.session
        for field in cls.base_fields:
            value = self.cleaned_data[field]
            if hasattr(cls, 'serialise_%s' % field):
                value = getattr(cls, 'serialise_%s' % field)(value)
            session[field] = value


class PaymentMethodChoiceForm(SendMoneyForm):
    payment_method = forms.ChoiceField(error_messages={
        'required': _('Please choose how you want to send money')
    }, choices=PaymentMethod.django_choices())

    def __init__(self, show_bank_transfer_first=False, **kwargs):
        super().__init__(**kwargs)
        if show_bank_transfer_first:
            self['payment_method'].field.choices = reversed(self['payment_method'].field.choices)
        if not check_payment_service_available():
            self.fields['payment_method'].initial = PaymentMethod.bank_transfer.name
            self.fields['payment_method'].disabled = True


class PrisonerDetailsForm(SendMoneyForm):
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
    serialise_prisoner_dob = serialise_date
    unserialise_prisoner_dob = unserialise_date
    error_messages = {
        'connection': _('This service is currently unavailable'),
        'not_found': _('No prisoner matches the details you’ve supplied'),
    }

    shared_api_client_lock = threading.RLock()
    shared_api_client = None

    @classmethod
    def get_prison_set(cls):
        return set()

    @classmethod
    def get_api_client(cls, reconnect=False):
        with cls.shared_api_client_lock:
            if reconnect or not cls.shared_api_client:
                cls.shared_api_client = get_api_client()
            return cls.shared_api_client

    def __init__(self, **kwargs):
        if isinstance(kwargs.get('data', {}).get('prisoner_dob'), datetime.date):
            prisoner_dob = kwargs['data'].pop('prisoner_dob')
            kwargs['data'].update({
                'prisoner_dob_0': prisoner_dob.day,
                'prisoner_dob_1': prisoner_dob.month,
                'prisoner_dob_2': prisoner_dob.year,
            })
        super().__init__(**kwargs)

    def lookup_prisoner(self, **filters):
        api_client = self.get_api_client()
        try:
            return api_client.prisoner_validity().get(**filters)
        except HttpClientError as e:
            if e.response.status_code != 401:
                raise
        api_client = self.get_api_client(reconnect=True)
        return api_client.prisoner_validity().get(**filters)

    def clean_prisoner_number(self):
        prisoner_number = self.cleaned_data.get('prisoner_number')
        if prisoner_number:
            prisoner_number = prisoner_number.upper()
        return prisoner_number

    def is_prisoner_known(self):
        prisoner_number = self.cleaned_data['prisoner_number']
        prisoner_dob = serialise_date(self.cleaned_data['prisoner_dob'])
        try:
            filters = {
                'prisoner_number': prisoner_number,
                'prisoner_dob': prisoner_dob,
            }
            prison_set = self.get_prison_set()
            if prison_set:
                filters['prisons'] = ','.join(sorted(prison_set))
            prisoners = self.lookup_prisoner(**filters)
            assert prisoners['count'] == len(prisoners['results']) == 1
            prisoner = prisoners['results'][0]
            return prisoner and prisoner['prisoner_number'] == prisoner_number \
                and prisoner['prisoner_dob'] == prisoner_dob
        except (HttpNotFoundError, KeyError, IndexError, AssertionError):
            pass
        return False

    def clean(self):
        try:
            if not self.errors and not self.is_prisoner_known():
                raise ValidationError(self.error_messages['not_found'], code='not_found')
        except (SlumberHttpBaseException, RequestException, OAuth2Error):
            logger.exception('Could not look up prisoner validity')
            raise ValidationError(self.error_messages['connection'], code='connection')
        return self.cleaned_data


class BankTransferPrisonerDetailsForm(PrisonerDetailsForm):
    @classmethod
    def get_prison_set(cls):
        return set(filter(None, settings.BANK_TRANSFER_PRISONS.split(',')))


class DebitCardPrisonerDetailsForm(PrisonerDetailsForm):
    field_order = ('prisoner_name', 'prisoner_dob', 'prisoner_number',)
    prisoner_name = forms.CharField(
        label=_('Prisoner name'),
        max_length=250,
    )

    @classmethod
    def get_prison_set(cls):
        return set(filter(None, settings.DEBIT_CARD_PRISONS.split(',')))


class DebitCardAmountForm(SendMoneyForm):
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
    serialise_amount = serialise_amount
    unserialise_amount = unserialise_amount


class BankTransferEmailForm(SendMoneyForm):
    email = forms.EmailField(label=_('Your email address'))
