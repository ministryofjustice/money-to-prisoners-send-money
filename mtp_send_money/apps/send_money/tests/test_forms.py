import logging
import threading
import time
import unittest
from unittest import mock

from django.utils.crypto import get_random_string
import responses

from send_money.forms import (
    PaymentMethodChoiceForm,
    BankTransferPrisonerDetailsForm,
    DebitCardPrisonerDetailsForm, DebitCardAmountForm,
)
from send_money.models import PaymentMethod
from send_money.tests import mock_auth, patch_gov_uk_pay_availability_check
from send_money.utils import api_url, get_api_session

logger = logging.getLogger('mtp')


class FormTestCase(unittest.TestCase):
    form_class = NotImplemented

    @classmethod
    def make_valid_tests(cls, data_sets):
        def make_method(input_data):
            def test(self):
                with patch_gov_uk_pay_availability_check():
                    form = self.form_class(data=input_data)
                    self.assertFormValid(form)

            return test

        for data_set in data_sets:
            setattr(cls, 'test_valid__%s' % data_set['name'], make_method(data_set['input_data']))

    @classmethod
    def make_invalid_tests(cls, data_sets):
        def make_method(input_data):
            def test(self):
                with patch_gov_uk_pay_availability_check():
                    form = self.form_class(data=input_data)
                    self.assertFormInvalid(form)

            return test

        for data_set in data_sets:
            setattr(cls, 'test_invalid__%s' % data_set['name'], make_method(data_set['input_data']))

    def assertFormValid(self, form):  # noqa
        is_valid = form.is_valid()
        self.assertTrue(is_valid, msg='\n\n%s' % form.errors.as_text())

    def assertFormInvalid(self, form):  # noqa
        is_valid = form.is_valid()
        self.assertFalse(is_valid)


class PaymentMethodChoiceFormTestCase(FormTestCase):
    form_class = PaymentMethodChoiceForm


PaymentMethodChoiceFormTestCase.make_valid_tests(
    {
        'name': method_choice.name,
        'input_data': {
            'payment_method': method_choice.name
        }
    }
    for method_choice in PaymentMethod
)
PaymentMethodChoiceFormTestCase.make_invalid_tests([
    {
        'name': 'no_input_data',
        'input_data': {}
    },
    {
        'name': 'empty_input_data',
        'input_data': {
            'payment_method': ''
        }
    },
])
PaymentMethodChoiceFormTestCase.make_invalid_tests(
    {
        'name': 'random_data_%s' % i,
        'input_data': {
            'payment_method': get_random_string(length=8)
        }
    }
    for i in range(3)
)


class PrisonerDetailsFormTestCase(FormTestCase):
    def assertFormValid(self, form):  # noqa
        with responses.RequestsMock() as rsps, \
                mock.patch('send_money.forms.PrisonerDetailsForm.get_api_session') as mocked_api_session:
            mocked_api_session.side_effect = get_api_session
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/prisoner_validity/'),
                json={
                    'count': 1,
                    'results': [{
                        'prisoner_number': 'A1234AB',
                        'prisoner_dob': '1980-10-05',
                    }],
                },
                status=200,
            )
            self.assertTrue(form.is_valid(), msg='\n\n%s' % form.errors.as_text())

    def assertFormInvalid(self, form):  # noqa
        with mock.patch('send_money.utils.api_client') as mocked_api_client:
            is_valid = form.is_valid()
        self.assertEqual(mocked_api_client.call_count, 0,
                         'api_client called!')
        self.assertEqual(mocked_api_client.authenticate.call_count, 0,
                         'api_client.authenticate called!')
        self.assertEqual(mocked_api_client.get_authenticated_connection.call_count, 0,
                         'api_client.get_authenticated_connection called!')
        self.assertFalse(is_valid)


class BankTransferPrisonerDetailsFormTestCase(PrisonerDetailsFormTestCase):
    form_class = BankTransferPrisonerDetailsForm

    def test_session_expiry(self):
        from mtp_common.auth.api_client import get_request_token_url

        form = self.form_class(data={
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        })
        create_session_calls = []

        def mocked_get_api_session(reconnect=False):
            create_session_calls.append(reconnect)
            return get_api_session()

        with responses.RequestsMock() as rsps, \
                mock.patch('send_money.forms.PrisonerDetailsForm.get_api_session') as mocked_api_session:
            mocked_api_session.side_effect = mocked_get_api_session
            rsps.add(
                rsps.POST,
                get_request_token_url(),
                json={
                    'token_type': 'Bearer',
                    'scope': 'read write',
                    'access_token': get_random_string(length=30),
                    'refresh_token': get_random_string(length=30),
                    'expires_in': 0,
                },
                status=200,
            )
            rsps.add(
                rsps.POST,
                get_request_token_url(),
                json={
                    'token_type': 'Bearer',
                    'scope': 'read write',
                    'access_token': get_random_string(length=30),
                    'refresh_token': get_random_string(length=30),
                    'expires_in': 3600,
                },
                status=200,
            )
            rsps.add(
                rsps.GET,
                api_url('/prisoner_validity/'),
                json={
                    'count': 1,
                    'results': [{
                        'prisoner_number': 'A1234AB',
                        'prisoner_dob': '1980-10-05',
                    }],
                },
                status=200,
            )
            self.assertTrue(form.is_valid())
        self.assertSequenceEqual(create_session_calls, [False, True])

    @mock.patch('send_money.forms.get_api_session')
    def test_validation_check_concurrency(self, mocked_api_session):
        form_class = self.form_class
        form_class.shared_api_session = None
        lock = threading.RLock()
        finished = threading.Event()
        concurrency = 5
        runs = 0
        successes = 0

        def delayed_response():
            logger.debug('Call to API takes 1 second')
            time.sleep(1)
            logger.debug('API call returning')
            return {
                'count': 1,
                'results': [{
                    'prisoner_number': 'A1234AB',
                    'prisoner_dob': '1980-10-05',
                }]
            }

        mocked_api_call = mocked_api_session().get().json
        mocked_api_call.side_effect = delayed_response
        setup_call_count = mocked_api_session.call_count

        class TestThread(threading.Thread):
            def run(self):
                nonlocal runs, successes

                form = form_class(data={
                    'prisoner_number': 'A1234AB',
                    'prisoner_dob_0': '5',
                    'prisoner_dob_1': '10',
                    'prisoner_dob_2': '1980',
                })
                is_valid = form.is_valid()
                with lock:
                    runs += 1
                    if is_valid:
                        successes += 1
                    if runs == concurrency:
                        finished.set()

        with patch_gov_uk_pay_availability_check():
            for _ in range(concurrency):
                TestThread().start()
        finished.wait()
        self.assertEqual(mocked_api_session.call_count, setup_call_count + 1, 'get_api_session called more than once, '
                                                                              'but the response should be shared')
        self.assertEqual(mocked_api_call.call_count, concurrency, 'validity should be called once for each thread')
        self.assertEqual(successes, concurrency, 'all threads should report valid forms')


BankTransferPrisonerDetailsFormTestCase.make_valid_tests([
    {
        'name': 'normal',
        'input_data': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'lowercase',
        'input_data': {
            'prisoner_number': 'a1234ab',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'short_year',
        'input_data': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '80',

        }
    },
])
BankTransferPrisonerDetailsFormTestCase.make_invalid_tests([
    {
        'name': 'no_data',
        'input_data': {}
    },
    {
        'name': 'missing_prisoner_number',
        'input_data': {
            'prisoner_number': '',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'prisoner_number',
        'input_data': {
            'prisoner_number': 'A12346',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'missing_prisoner_dob',
        'input_data': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '',
            'prisoner_dob_1': '',
            'prisoner_dob_2': '',
        }
    },
    {
        'name': 'missing_prisoner_dob_day',
        'input_data': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        },
    },
    {
        'name': 'missing_prisoner_dob_month',
        'input_data': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '',
            'prisoner_dob_2': '1980',
        },
    },
    {
        'name': 'missing_prisoner_dob_year',
        'input_data': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '',
        },
    },
    {
        'name': 'dob_format',
        'input_data': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': 'Oct',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'invalid_dob',
        'input_data': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '31',
            'prisoner_dob_1': '2',
            'prisoner_dob_2': '1980',
        }
    },
])


class DebitCardPrisonerDetailsFormTestCase(PrisonerDetailsFormTestCase):
    form_class = DebitCardPrisonerDetailsForm


DebitCardPrisonerDetailsFormTestCase.make_valid_tests([
    {
        'name': 'normal',
        'input_data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'lowercase',
        'input_data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'a1234ab',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'short_year',
        'input_data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '80',

        }
    },
    {
        'name': 'another',
        'input_data': {
            'prisoner_name': 'random name',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',

        }
    },
])
DebitCardPrisonerDetailsFormTestCase.make_invalid_tests([
    {
        'name': 'no_data',
        'input_data': {}
    },
    {
        'name': 'missing_name',
        'input_data': {
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'empty_name',
        'input_data': {
            'prisoner_name': '',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'card_number',
        'input_data': {
            'prisoner_name': '4444333322221111',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'missing_prisoner_number',
        'input_data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': '',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'prisoner_number',
        'input_data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A12346',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'missing_prisoner_dob',
        'input_data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '',
            'prisoner_dob_1': '',
            'prisoner_dob_2': '',
        }
    },
    {
        'name': 'missing_prisoner_dob_day',
        'input_data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        },
    },
    {
        'name': 'missing_prisoner_dob_month',
        'input_data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '',
            'prisoner_dob_2': '1980',
        },
    },
    {
        'name': 'missing_prisoner_dob_year',
        'input_data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '',
        },
    },
    {
        'name': 'dob_format',
        'input_data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '5',
            'prisoner_dob_1': 'Oct',
            'prisoner_dob_2': '1980',
        }
    },
    {
        'name': 'invalid_dob',
        'input_data': {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1234AB',
            'prisoner_dob_0': '31',
            'prisoner_dob_1': '2',
            'prisoner_dob_2': '1980',
        }
    },
])


class DebitCardAmountFormTestCase(FormTestCase):
    form_class = DebitCardAmountForm


DebitCardAmountFormTestCase.make_valid_tests([
    {
        'name': 'amount_1',
        'input_data': {
            'amount': '120.45',
        }
    },
    {
        'name': 'amount_2',
        'input_data': {
            'amount': '120.00',
        }
    },
    {
        'name': 'amount_3',
        'input_data': {
            'amount': '200.00',
        }
    },
    {
        'name': 'integer',
        'input_data': {
            'amount': '10',
        }
    },
    {
        'name': 'pence_only_1',
        'input_data': {
            'amount': '0.13',
        }
    },
    {
        'name': 'pence_only_2',
        'input_data': {
            'amount': '.13',
        }
    },
])
DebitCardAmountFormTestCase.make_invalid_tests([
    {
        'name': 'no_data',
        'input_data': {}
    },
    {
        'name': 'missing_amount',
        'input_data': {
            'amount': '',
        }
    },
    {
        'name': 'zero_amount_1',
        'input_data': {
            'amount': '0',
        }
    },
    {
        'name': 'zero_amount_2',
        'input_data': {
            'amount': '0.00',
        }
    },
    {
        'name': 'too_many_pence_digits',
        'input_data': {
            'amount': '10.310',
        }
    },
    {
        'name': 'negative',
        'input_data': {
            'amount': '-10',
        }
    },
    {
        'name': 'negative_pence',
        'input_data': {
            'amount': '-0.10',
        }
    },
    {
        'name': 'too_much_1',
        'input_data': {
            'amount': '200.01',
        }
    },
    {
        'name': 'too_much_2',
        'input_data': {
            'amount': '1000',
        }
    },
    {
        'name': 'pounds',
        'input_data': {
            'amount': '£10.20',
        }
    },
    {
        'name': 'pound_integer',
        'input_data': {
            'amount': '£10',
        }
    },
])
