import logging
import threading
import time
from unittest import mock

from django.test.testcases import SimpleTestCase
from django.test import override_settings
from django.utils.crypto import get_random_string
import responses

from send_money.forms import (
    PaymentMethodChoiceForm,
    BankTransferPrisonerDetailsForm,
    DebitCardPrisonerDetailsForm, DebitCardAmountForm,
)
from send_money.models import PaymentMethodBankTransferEnabled
from send_money.tests import mock_auth, patch_gov_uk_pay_availability_check
from send_money.utils import api_url, get_api_session

logger = logging.getLogger('mtp')


class FormTestCase(SimpleTestCase):
    form_class = NotImplemented

    @classmethod
    def make_valid_tests(cls, data_sets):
        def make_method(input_data):
            def test(self):
                with patch_gov_uk_pay_availability_check():
                    form = self.form_class(**input_data)
                    self.assertFormValid(form)

            return test

        for data_set in data_sets:
            setattr(cls, 'test_valid__%s' % data_set['name'], make_method(data_set['input_data']))

    @classmethod
    def make_invalid_tests(cls, data_sets):
        def make_method(input_data, key_error):
            def test(self):
                if key_error:
                    with self.assertRaises(KeyError):
                        form = self.form_class(**input_data)
                else:
                    with patch_gov_uk_pay_availability_check():
                        form = self.form_class(**input_data)
                        self.assertFormInvalid(form)

            return test

        for data_set in data_sets:
            setattr(
                cls,
                'test_invalid__%s' % data_set['name'],
                make_method(
                    data_set['input_data'],
                    key_error=data_set.get('key_error', False)
                )
            )

    def assertFormValid(self, form):  # noqa: N802
        is_valid = form.is_valid()
        self.assertTrue(is_valid, msg='\n\n%s' % form.errors.as_text())

    def assertFormInvalid(self, form):  # noqa: N802
        is_valid = form.is_valid()
        self.assertFalse(is_valid)


@override_settings(BANK_TRANSFERS_ENABLED=True)
class PaymentMethodChoiceFormTestCase(FormTestCase):
    form_class = PaymentMethodChoiceForm

    @mock.patch('send_money.forms.check_payment_service_available', return_value=(False, 'Bad bad, not good'))
    @override_settings(BANK_TRANSFERS_ENABLED=False)
    def test_initial_not_set_on_availability_fail_if_bank_transfer_not_enabled(self, *args):
        form = self.form_class()
        self.assertFalse(bool(form.fields['payment_method'].initial))
        self.assertEqual(form.fields['payment_method'].message_to_users, 'Bad bad, not good')


PaymentMethodChoiceFormTestCase.make_valid_tests(
    {
        'name': method_choice.name,
        'input_data': {
            'data': {
                'payment_method': method_choice.name
            }
        }
    }
    for method_choice in PaymentMethodBankTransferEnabled
)
PaymentMethodChoiceFormTestCase.make_invalid_tests([
    {
        'name': 'no_input_data',
        'input_data': {}
    },
    {
        'name': 'empty_input_data',
        'input_data': {
            'data': {
                'payment_method': ''
            }
        }
    },
])
PaymentMethodChoiceFormTestCase.make_invalid_tests(
    {
        'name': 'random_data_%s' % i,
        'input_data': {
            'data': {
                'payment_method': get_random_string(length=8)
            }
        }
    }
    for i in range(3)
)


class PrisonerDetailsFormTestCase(FormTestCase):
    def assertFormValid(self, form):  # noqa: N802
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

    def assertFormInvalid(self, form):  # noqa: N802
        with mock.patch('send_money.utils.api_client') as mocked_api_client:
            is_valid = form.is_valid()
        self.assertEqual(mocked_api_client.call_count, 0,
                         'api_client called!')
        self.assertEqual(mocked_api_client.authenticate.call_count, 0,
                         'api_client.authenticate called!')
        self.assertEqual(mocked_api_client.get_authenticated_connection.call_count, 0,
                         'api_client.get_authenticated_connection called!')
        self.assertFalse(is_valid)


@override_settings(BANK_TRANSFERS_ENABLED=True)
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
            'data': {
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'lowercase',
        'input_data': {
            'data': {
                'prisoner_number': 'a1234ab',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'short_year',
        'input_data': {
            'data': {
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '80',
            }
        }
    },
])
BankTransferPrisonerDetailsFormTestCase.make_invalid_tests([
    {
        'name': 'no_data',
        'input_data': {}
    },
    {
        'name': 'empty_data',
        'input_data': {'data': {}}
    },
    {
        'name': 'missing_prisoner_number',
        'input_data': {
            'data': {
                'prisoner_number': '',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'prisoner_number',
        'input_data': {
            'data': {
                'prisoner_number': 'A12346',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'missing_prisoner_dob',
        'input_data': {
            'data': {
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '',
                'prisoner_dob_1': '',
                'prisoner_dob_2': '',
            }
        }
    },
    {
        'name': 'missing_prisoner_dob_day',
        'input_data': {
            'data': {
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        },
    },
    {
        'name': 'missing_prisoner_dob_month',
        'input_data': {
            'data': {
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '',
                'prisoner_dob_2': '1980',
            }
        },
    },
    {
        'name': 'missing_prisoner_dob_year',
        'input_data': {
            'data': {
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '',
            }
        },
    },
    {
        'name': 'dob_format',
        'input_data': {
            'data': {
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': 'Oct',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'invalid_dob',
        'input_data': {
            'data': {
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '31',
                'prisoner_dob_1': '2',
                'prisoner_dob_2': '1980',
            }
        }
    },
])


class DebitCardPrisonerDetailsFormTestCase(PrisonerDetailsFormTestCase):
    form_class = DebitCardPrisonerDetailsForm


DebitCardPrisonerDetailsFormTestCase.make_valid_tests([
    {
        'name': 'normal',
        'input_data': {
            'data': {
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'lowercase',
        'input_data': {
            'data': {
                'prisoner_name': 'John Smith',
                'prisoner_number': 'a1234ab',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'short_year',
        'input_data': {
            'data': {
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '80',
            }
        }
    },
    {
        'name': 'another',
        'input_data': {
            'data': {
                'prisoner_name': 'random name',
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
])
DebitCardPrisonerDetailsFormTestCase.make_invalid_tests([
    {
        'name': 'no_data',
        'input_data': {}
    },
    {
        'name': 'empty_data',
        'input_data': {'data': {}}
    },
    {
        'name': 'missing_name',
        'input_data': {
            'data': {
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'empty_name',
        'input_data': {
            'data': {
                'prisoner_name': '',
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'card_number',
        'input_data': {
            'data': {
                'prisoner_name': '4444333322221111',
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'missing_prisoner_number',
        'input_data': {
            'data': {
                'prisoner_name': 'John Smith',
                'prisoner_number': '',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'prisoner_number',
        'input_data': {
            'data': {
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A12346',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'missing_prisoner_dob',
        'input_data': {
            'data': {
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '',
                'prisoner_dob_1': '',
                'prisoner_dob_2': '',
            }
        }
    },
    {
        'name': 'missing_prisoner_dob_day',
        'input_data': {
            'data': {
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }
        },
    },
    {
        'name': 'missing_prisoner_dob_month',
        'input_data': {
            'data': {
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '',
                'prisoner_dob_2': '1980',
            }
        },
    },
    {
        'name': 'missing_prisoner_dob_year',
        'input_data': {
            'data': {
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '',
            }
        },
    },
    {
        'name': 'dob_format',
        'input_data': {
            'data': {
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '5',
                'prisoner_dob_1': 'Oct',
                'prisoner_dob_2': '1980',
            }
        }
    },
    {
        'name': 'invalid_dob',
        'input_data': {
            'data': {
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A1234AB',
                'prisoner_dob_0': '31',
                'prisoner_dob_1': '2',
                'prisoner_dob_2': '1980',
            }
        }
    },
])


@override_settings(
    PRISONER_CAPPING_ENABLED=True
)
class DebitCardAmountValidFormTestCase(FormTestCase):
    form_class = DebitCardAmountForm

    def assertFormValid(self, form):  # noqa: N802
        with mock.patch.object(self.form_class, 'get_api_session') as mock_session, responses.RequestsMock() as rsps:
            mock_session.side_effect = lambda reconnect: get_api_session()
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/prisoner_account_balances/{form.prisoner_number}'),
                json={
                    'combined_account_balance': 3000
                },
                status=200,
            )
            self.assertTrue(form.is_valid(), msg='\n\n%s' % form.errors.as_text())


class DebitCardAmountNotValidFormTestCase(FormTestCase):
    form_class = DebitCardAmountForm

    def assertFormInvalid(self, form):  # noqa: N802
        with mock.patch('send_money.utils.api_client') as mocked_api_client:
            is_valid = form.is_valid()
        self.assertEqual(mocked_api_client.call_count, 0,
                         'api_client called!')
        self.assertEqual(mocked_api_client.authenticate.call_count, 0,
                         'api_client.authenticate called!')
        self.assertEqual(mocked_api_client.get_authenticated_connection.call_count, 0,
                         'api_client.get_authenticated_connection called!')
        self.assertFalse(is_valid)


DebitCardAmountValidFormTestCase.make_valid_tests([
    {
        'name': 'amount_1',
        'input_data': {
            'data': {
                'amount': '120.45',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'amount_2',
        'input_data': {
            'data': {
                'amount': '120.00',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'amount_3',
        'input_data': {
            'data': {
                'amount': '200.00',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'integer',
        'input_data': {
            'data': {
                'amount': '10',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'pence_only_1',
        'input_data': {
            'data': {
                'amount': '0.13',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'pence_only_2',
        'input_data': {
            'data': {
                'amount': '.13',
            },
            'prisoner_number': '24601'
        }
    },
])
DebitCardAmountNotValidFormTestCase.make_invalid_tests([
    {
        'name': 'no_data',
        'input_data': {
            'data': {}
        },
        'key_error': True
    },
    {
        'name': 'no_amount',
        'input_data': {
            'data': {
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'no_prisoner_number',
        'input_data': {
            'data': {
                'amount': '10.310',
            },
        },
        'key_error': True
    },
    {
        'name': 'missing_amount',
        'input_data': {
            'data': {
                'amount': '',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'zero_amount_1',
        'input_data': {
            'data': {
                'amount': '0',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'zero_amount_2',
        'input_data': {
            'data': {
                'amount': '0.00',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'too_many_pence_digits',
        'input_data': {
            'data': {
                'amount': '10.310',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'negative',
        'input_data': {
            'data': {
                'amount': '-10',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'negative_pence',
        'input_data': {
            'data': {
                'amount': '-0.10',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'too_much_1',
        'input_data': {
            'data': {
                'amount': '200.01',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'too_much_2',
        'input_data': {
            'data': {
                'amount': '1000',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'pounds',
        'input_data': {
            'data': {
                'amount': '£10.20',
            },
            'prisoner_number': '24601'
        }
    },
    {
        'name': 'pound_integer',
        'input_data': {
            'data': {
                'amount': '£10',
            },
            'prisoner_number': '24601'
        }
    },
])
