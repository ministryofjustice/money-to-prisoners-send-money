import unittest
from unittest import mock

from django.conf import settings
from django.http import HttpRequest
from django.utils.crypto import get_random_string
from moj_auth import urljoin
from moj_auth.api_client import REQUEST_TOKEN_URL
import responses

from send_money.forms import PaymentMethod, SendMoneyForm
from send_money.utils import lenient_unserialise_date, serialise_date


class SendMoneyFormTestCase(unittest.TestCase):
    @classmethod
    def api_url(cls, path):
        return urljoin(settings.API_URL, path)

    @classmethod
    def mock_auth(cls, rsps):
        rsps.add(
            rsps.POST,
            REQUEST_TOKEN_URL,
            json={
                'access_token': get_random_string(length=30),
                'refresh_token': get_random_string(length=30)
            },
            status=200,
        )
        rsps.add(
            rsps.GET,
            urljoin(settings.API_URL, 'users/', settings.SHARED_API_USERNAME),
            json={
                'pk': 1,
                'first_name': 'Send Money',
                'last_name': 'Shared',
            },
            status=200,
        )

    def assertFormInvalid(self, form, mocked_api_client=None):  # noqa
        is_valid = form.is_valid()
        if mocked_api_client:
            self.assertEqual(mocked_api_client.call_count, 0,
                             'api_client called!')
            self.assertEqual(mocked_api_client.authenticate.call_count, 0,
                             'api_client.authenticate called!')
            self.assertEqual(mocked_api_client.get_connection.call_count, 0,
                             'api_client.get_connection called!')
        self.assertFalse(is_valid)


valid_data_sets = [
    {
        'name': 'debit_card_1',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '120.45',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'debit_card_2',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '5/10/1980',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '12000.00',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'bank_transfer_1',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '10',
            'payment_method': PaymentMethod.bank_transfer,
        },
    },
    {
        'name': 'bank_transfer_2',
        'prisoner_details': {
            'prisoner_number': 'a1234ab',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '100',
            'payment_method': PaymentMethod.bank_transfer,
        },
    },
]


def normalise_prisoner_details(prisoner_details):
    prisoner_details['prisoner_number'] = prisoner_details['prisoner_number'].upper()
    prisoner_details['prisoner_dob'] = serialise_date(
        lenient_unserialise_date(prisoner_details['prisoner_dob'])
    )
    return prisoner_details


def make_valid_test(name, prisoner_details, data):
    def test(self):
        with responses.RequestsMock() as rsps:
            self.mock_auth(rsps)
            rsps.add(
                rsps.GET,
                self.api_url('/prisoner_validity/'),
                json={
                    'count': 1,
                    'results': [normalise_prisoner_details(prisoner_details)],
                },
                status=200,
            )
            data.update(prisoner_details)
            form = SendMoneyForm(request=HttpRequest(), data=data)
            self.assertTrue(form.is_valid(), msg='\n\n%s' % form.errors.as_text())
    return test


for valid_data_set in valid_data_sets:
    setattr(SendMoneyFormTestCase, 'test_valid__%s' % valid_data_set['name'],
            make_valid_test(**valid_data_set))


invalid_data_sets = [
    {
        'name': 'empty_form',
        'prisoner_details': {},
        'data': {},
    },
    {
        'name': 'missing_name',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'amount': '120.45',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'missing_prisoner_number',
        'prisoner_details': {
            'prisoner_number': '',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '120.45',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'missing_prisoner_dob',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '120.45',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'missing_amount',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'missing_payment_method',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '120.45',
            'payment_method': '',
        },
    },
    {
        'name': 'prisoner_number',
        'prisoner_details': {
            'prisoner_number': 'A12346',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '120.45',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'prisoner_dob',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '5 Oct 1988',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '120.45',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'amount_1',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '0',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'amount_2',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '£10',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'amount_3',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '100.456',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'payment_method',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '100.45',
            'payment_method': 'postal_order',
        },
    },
]


def make_invalid_test(name, prisoner_details, data):
    @mock.patch('send_money.forms.api_client')
    def test(self, mocked_api_client):
        data.update(prisoner_details)
        form = SendMoneyForm(request=HttpRequest(), data=data)
        self.assertFormInvalid(form, mocked_api_client)
    return test


for invalid_data_set in invalid_data_sets:
    setattr(SendMoneyFormTestCase, 'test_invalid__%s' % invalid_data_set['name'],
            make_invalid_test(**invalid_data_set))
