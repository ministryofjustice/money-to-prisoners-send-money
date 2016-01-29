import unittest
from unittest import mock

from django.http import HttpRequest
import responses

from send_money.forms import PaymentMethod, SendMoneyForm
from send_money.tests import mock_auth, split_prisoner_dob_for_post
from send_money.utils import lenient_unserialise_date, serialise_date, api_url


class SendMoneyFormTestCase(unittest.TestCase):

    def assertFormInvalid(self, form, mocked_api_client=None):  # noqa
        is_valid = form.is_valid()
        if mocked_api_client:
            self.assertEqual(mocked_api_client.call_count, 0,
                             'api_client called!')
            self.assertEqual(mocked_api_client.authenticate.call_count, 0,
                             'api_client.authenticate called!')
            self.assertEqual(mocked_api_client.get_authenticated_connection.call_count, 0,
                             'api_client.get_authenticated_connection called!')
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
        'name': 'debit_card_3',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '1000000.00',
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
    """
    Normalises the input prisoner details into the canonical form
    in the form that the API would provide.
    """
    prisoner_details['prisoner_number'] = prisoner_details['prisoner_number'].upper()
    prisoner_details['prisoner_dob'] = serialise_date(
        lenient_unserialise_date(prisoner_details['prisoner_dob'])
    )
    return prisoner_details


def make_valid_test(name, prisoner_details, data):
    def test(self):
        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/prisoner_validity/'),
                json={
                    'count': 1,
                    'results': [normalise_prisoner_details(prisoner_details)],
                },
                status=200,
            )
            data.update(split_prisoner_dob_for_post(prisoner_details))
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
        'name': 'amount_4',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '-10',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'amount_5',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'amount': '1000000.01',
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
    @mock.patch('send_money.utils.api_client')
    def test(self, mocked_api_client):
        data.update(split_prisoner_dob_for_post(prisoner_details))
        form = SendMoneyForm(request=HttpRequest(), data=data)
        self.assertFormInvalid(form, mocked_api_client)
    return test


for invalid_data_set in invalid_data_sets:
    setattr(SendMoneyFormTestCase, 'test_invalid__%s' % invalid_data_set['name'],
            make_invalid_test(**invalid_data_set))
