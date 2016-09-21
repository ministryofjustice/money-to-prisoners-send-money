import datetime
import decimal
import logging

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from form_error_reporting import GARequestErrorReportingMixin
from mtp_common.forms.fields import SplitDateField
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException
from slumber.exceptions import HttpNotFoundError, SlumberHttpBaseException

from send_money.models import PaymentMethod
from send_money.utils import (
    serialise_amount, unserialise_amount, serialise_date, unserialise_date,
    get_api_client, validate_prisoner_number
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


class PrisonerDetailsForm(SendMoneyForm):
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
    serialise_prisoner_dob = serialise_date
    unserialise_prisoner_dob = unserialise_date

    def __init__(self, **kwargs):
        if isinstance(kwargs.get('data', {}).get('prisoner_dob'), datetime.date):
            prisoner_dob = kwargs['data'].pop('prisoner_dob')
            kwargs['data'].update({
                'prisoner_dob_0': prisoner_dob.day,
                'prisoner_dob_1': prisoner_dob.month,
                'prisoner_dob_2': prisoner_dob.year,
            })
        super().__init__(**kwargs)

    def clean_prisoner_number(self):
        prisoner_number = self.cleaned_data.get('prisoner_number')
        if prisoner_number:
            prisoner_number = prisoner_number.upper()
        return prisoner_number

    def is_prisoner_known(self):
        prisoner_number = self.cleaned_data['prisoner_number']
        prisoner_dob = serialise_date(self.cleaned_data['prisoner_dob'])
        try:
            client = get_api_client()
            prisoners = client.prisoner_validity().get(prisoner_number=prisoner_number,
                                                       prisoner_dob=prisoner_dob)
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
                raise ValidationError(
                    message=[_('No prisoner matches the details you’ve supplied, '
                               'please ask the prisoner to check your details are correct')],
                    code='not_found'
                )
        except (SlumberHttpBaseException, RequestException, OAuth2Error):
            logger.exception('Could not look up prisoner validity')
            raise ValidationError(
                message=[_('This service is currently unavailable')],
                code='connection')
        return self.cleaned_data


class BankTransferPrisonerDetailsForm(PrisonerDetailsForm):
    pass


class DebitCardPrisonerDetailsForm(PrisonerDetailsForm):
    field_order = ('prisoner_name', 'prisoner_dob', 'prisoner_number',)
    prisoner_name = forms.CharField(
        label=_('Prisoner name'),
        max_length=250,
    )


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
