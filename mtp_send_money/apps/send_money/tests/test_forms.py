import unittest
from unittest import mock

from django.http import HttpRequest
import responses

from send_money.forms import PaymentMethod, SendMoneyForm
from send_money.tests import mock_auth, normalise_prisoner_details, update_post_with_prisoner_details
from send_money.utils import api_url


class SendMoneyFormTestCase(unittest.TestCase):
    @classmethod
    def make_valid_tests(cls, data_sets):
        def make_method(name, prisoner_details, data):
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
                    update_post_with_prisoner_details(data, prisoner_details)
                    form = SendMoneyForm(request=HttpRequest(), data=data)
                    self.assertTrue(form.is_valid(), msg='\n\n%s' % form.errors.as_text())

            return test

        for data_set in data_sets:
            setattr(cls, 'test_valid__%s' % data_set['name'], make_method(**data_set))

    @classmethod
    def make_invalid_tests(cls, data_sets):
        def make_method(name, prisoner_details, data):
            @mock.patch('send_money.utils.api_client')
            def test(self, mocked_api_client):
                update_post_with_prisoner_details(data, prisoner_details)
                form = SendMoneyForm(request=HttpRequest(), data=data)
                self.assertFormInvalid(form, mocked_api_client)

            return test

        for data_set in data_sets:
            setattr(cls, 'test_invalid__%s' % data_set['name'], make_method(**data_set))

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


SendMoneyFormTestCase.make_valid_tests([
    {
        'name': 'debit_card_1',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
            'amount': '1000000.00',
            'payment_method': PaymentMethod.debit_card,
        },
    },
    {
        'name': 'debit_card_no_email',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
            'amount': '100',
            'payment_method': PaymentMethod.bank_transfer,
        },
    },
    {
        'name': 'bank_transfer_short_year',
        'prisoner_details': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob': '1980-10-05',
        },
        'data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '80',
            'email': 'sender@outside.local',
            'amount': '100',
            'payment_method': PaymentMethod.bank_transfer,
        },
    },
])

SendMoneyFormTestCase.make_invalid_tests([
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
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
            'email': 'sender@outside.local',
            'amount': '100.45',
            'payment_method': 'postal_order',
        },
    },
])
