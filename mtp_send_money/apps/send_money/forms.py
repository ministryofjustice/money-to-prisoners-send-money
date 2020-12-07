import datetime
import decimal
import logging
import threading

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.utils.translation import gettext, gettext_lazy as _
from form_error_reporting import GARequestErrorReportingMixin
from mtp_common.auth.exceptions import HttpNotFoundError
from mtp_common.forms.fields import SplitDateField
from oauthlib.oauth2 import OAuth2Error, TokenExpiredError
from requests.exceptions import RequestException

from send_money.models import PaymentMethodBankTransferDisabled
from send_money.utils import (
    serialise_amount, unserialise_amount, serialise_date, unserialise_date,
    RejectCardNumberValidator, validate_prisoner_number,
    get_api_session, check_payment_service_available,
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

        try:
            data = {
                field: get_value(field)
                for field in cls.base_fields
            }
        except KeyError:
            data = None

        extra_kwargs = {
            field: get_value(field)
            for field in getattr(cls, 'additional_fields_to_deserialize', [])
        }
        return cls(request=request, data=data, **extra_kwargs)

    def __init__(self, request=None, **kwargs):
        super().__init__(**kwargs)
        self.request = request

    def serialise_to_session(self):
        cls = self.__class__
        session = self.request.session
        for field in cls.base_fields:
            value = self.cleaned_data[field]
            if hasattr(cls, 'serialise_%s' % field):
                value = getattr(cls, 'serialise_%s' % field)(value)
            session[field] = value

        for field in getattr(cls, 'additional_fields_to_deserialize', []):
            session[field] = getattr(self, field, self.cleaned_data.get(field))


class PaymentMethodChoiceForm(SendMoneyForm):
    additional_fields_to_deserialize = ('payment_method',)

    def __init__(self, **kwargs):
        django_choices = PaymentMethodBankTransferDisabled.django_choices()
        self.base_fields['payment_method'] = forms.ChoiceField(
            error_messages={'required': _('Please choose how you want to send money')},
            choices=django_choices
        )

        payment_service_available, message_to_users = check_payment_service_available()
        if not payment_service_available:
            self.base_fields['payment_method'].message_to_users = message_to_users
            self.base_fields['payment_method'].disabled = True
        # Handle session deserialization of fields defined against instance manually :(
        if 'payment_method' in kwargs:
            kwargs['data']['payment_method'] = kwargs.pop('payment_method')
        super().__init__(**kwargs)


class PrisonerDetailsForm(SendMoneyForm):
    prisoner_dob = SplitDateField(
        label=_('Prisoner date of birth'),
        help_text=_('For example, 28 04 1996'),
    )
    prisoner_number = forms.CharField(
        label=_('Prisoner number'),
        help_text=_('For example, A1234BC'),
        max_length=7,
        validators=[validate_prisoner_number],
    )
    serialise_prisoner_dob = serialise_date
    unserialise_prisoner_dob = unserialise_date
    error_messages = {
        'connection': _('This service is currently unavailable'),
        'not_found': _('No prisoner matches the details you’ve supplied.'),
    }

    shared_api_session_lock = threading.RLock()
    shared_api_session = None

    @classmethod
    def get_prison_set(cls):
        return set()

    @classmethod
    def get_api_session(cls, reconnect=False):
        with cls.shared_api_session_lock:
            if reconnect or not cls.shared_api_session:
                cls.shared_api_session = get_api_session()
            return cls.shared_api_session

    def __init__(self, **kwargs):
        if isinstance((kwargs.get('data') or {}).get('prisoner_dob'), datetime.date):
            prisoner_dob = kwargs['data'].pop('prisoner_dob')
            kwargs['data'].update({
                'prisoner_dob_0': prisoner_dob.day,
                'prisoner_dob_1': prisoner_dob.month,
                'prisoner_dob_2': prisoner_dob.year,
            })
        super().__init__(**kwargs)

    def lookup_prisoner(self, **filters):
        session = self.get_api_session()
        try:
            return session.get('/prisoner_validity/', params=filters).json()
        except TokenExpiredError:
            pass
        except RequestException as e:
            if e.response.status_code != 401:
                raise
        session = self.get_api_session(reconnect=True)
        return session.get('/prisoner_validity/', params=filters).json()

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
        except (HttpNotFoundError, KeyError, IndexError, ValueError, AssertionError):
            pass
        return False

    def clean(self):
        try:
            if not self.errors and not self.is_prisoner_known():
                raise ValidationError(self.error_messages['not_found'], code='not_found')
        except (RequestException, OAuth2Error):
            logger.exception('Could not look up prisoner validity')
            raise ValidationError(self.error_messages['connection'], code='connection')
        return self.cleaned_data


class DebitCardPrisonerDetailsForm(PrisonerDetailsForm):
    field_order = ('prisoner_name', 'prisoner_dob', 'prisoner_number',)
    prisoner_name = forms.CharField(
        label=_('Prisoner name'),
        max_length=250,
        validators=[RejectCardNumberValidator()],
    )

    @classmethod
    def get_prison_set(cls):
        return set(filter(None, settings.DEBIT_CARD_PRISONS.split(',')))


class MaxAmountValidator(MaxValueValidator):
    message = (gettext('The amount you are trying to send is too large.') + ' ' +
               gettext('Please enter a smaller amount'))


class DebitCardAmountForm(SendMoneyForm):
    amount = forms.DecimalField(
        label=_('Amount'),
        min_value=decimal.Decimal('0.01'),
        decimal_places=2,
        validators=[MaxAmountValidator(decimal.Decimal('200'))],
        error_messages={
            'invalid': _('Enter as a number'),
            'min_value': _('Amount should be 1p or more'),
            'max_decimal_places': _('Only use 2 decimal places'),
        }
    )
    error_messages = {
        'connection': _('This service is currently unavailable'),
        'missing_prisoner_number': _('This service is currently unavailable'),
        'cap_exceeded': _(
            'You can’t send money to this person’s account. It has reached its limit for now. '
            'Please follow up with them about it.'
        )
    }
    serialise_amount = serialise_amount
    unserialise_amount = unserialise_amount
    max_lookup_tries = 2
    additional_fields_to_deserialize = ['prisoner_number']
    shared_api_session_lock = threading.RLock()
    shared_api_session = None

    def __init__(self, *args, **kwargs):
        self.prisoner_number = kwargs.pop('prisoner_number')
        super().__init__(*args, **kwargs)

    @classmethod
    def get_api_session(cls, reconnect=False):
        with cls.shared_api_session_lock:
            if reconnect or not cls.shared_api_session:
                cls.shared_api_session = get_api_session()
            return cls.shared_api_session

    def clean(self):
        try:
            if not self.errors and not self.is_account_balance_below_threshold():
                raise ValidationError(self.error_messages['cap_exceeded'], code='cap_exceeded')
        except (RequestException, OAuth2Error):
            logger.exception('Could not look up prisoner account balance')
            raise ValidationError(self.error_messages['connection'], code='connection')
        return self.cleaned_data

    def is_account_balance_below_threshold(self):
        if not settings.PRISONER_CAPPING_ENABLED:
            return True

        prisoner_account_balance_integer = self.lookup_prisoner_account_balance()['combined_account_balance']

        assert isinstance(prisoner_account_balance_integer, int), \
            f'expected NOMIS balance to be int but is {type(prisoner_account_balance_integer)}'

        prisoner_account_balance = decimal.Decimal(prisoner_account_balance_integer) / 100
        prisoner_account_balance += decimal.Decimal(self.data['amount'])
        return prisoner_account_balance <= settings.PRISONER_CAPPING_THRESHOLD_IN_POUNDS

    def lookup_prisoner_account_balance(self, tries=0):
        session = self.get_api_session(reconnect=(tries != 0))
        try:
            return session.get(f'/prisoner_account_balances/{self.prisoner_number}').json()
        except TokenExpiredError:
            pass
        except RequestException as e:
            if e.response.status_code != 401:
                raise
        if tries < self.max_lookup_tries:
            return self.lookup_prisoner_account_balance(tries=tries + 1)
        else:
            raise ValidationError(self.error_messages['connection'], code='connection')
