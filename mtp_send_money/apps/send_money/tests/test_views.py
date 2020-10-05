import datetime
from decimal import Decimal
import json
import logging
import time
from unittest import mock

from django.core import mail
from django.test import override_settings
from django.test.testcases import SimpleTestCase
from django.urls import reverse
from mtp_common.test_utils import silence_logger
from requests import ConnectionError
import responses

from send_money.models import PaymentMethodBankTransferEnabled as PaymentMethod
from send_money.tests import (
    BaseTestCase, mock_auth,
    patch_notifications, patch_gov_uk_pay_availability_check,
)
from send_money.views import should_be_capture_delayed
from send_money.utils import api_url, govuk_url, get_api_session


@override_settings(BANK_TRANSFERS_ENABLED=True)
class PaymentOptionAvailabilityTestCase(BaseTestCase):
    @patch_notifications()
    @patch_gov_uk_pay_availability_check()
    def test_locale_switches_based_on_browser_language(self):
        languages = (
            ('*', 'en-gb'),
            ('en', 'en-gb'),
            ('en-gb', 'en-gb'),
            ('en-GB, en, *', 'en-gb'),
            ('cy', 'cy'),
            ('cy, en-GB, en, *', 'cy'),
            ('en, cy, *', 'en-gb'),
            ('es', 'en-gb'),
        )
        with silence_logger(name='django.request', level=logging.ERROR):
            for accept_language, expected_slug in languages:
                response = self.client.get('/', HTTP_ACCEPT_LANGUAGE=accept_language)
                self.assertRedirects(response, '/%s/' % expected_slug)
                response = self.client.get('/terms/', HTTP_ACCEPT_LANGUAGE=accept_language)
                self.assertRedirects(response, '/%s/terms/' % expected_slug)

    @patch_notifications()
    @patch_gov_uk_pay_availability_check()
    def test_both_flows_accessible_when_enabled(self):
        response = self.client.get(self.root_url, follow=True)
        self.assertOnPage(response, 'choose_method')
        self.assertNotContains(response, 'Prisoner name')
        self.assertNotContains(response, 'Amount')


@patch_notifications()
@patch_gov_uk_pay_availability_check()
@override_settings(BANK_TRANSFERS_ENABLED=True)
class ChooseMethodViewTestCase(BaseTestCase):
    url = '/en-gb/'

    def test_shows_all_payment_options(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')
        self.assertResponseNotCacheable(response)
        content = response.content.decode('utf8')
        for method in PaymentMethod:
            self.assertIn('id_%s' % method.name, content)

    def test_session_reset_if_returning_to_page(self):
        response = self.client.post(self.url, data={
            'payment_method': PaymentMethod.debit_card.name
        }, follow=True)
        self.assertOnPage(response, 'prisoner_details_debit')
        response = self.client.get(self.url, follow=True)
        content = response.content.decode('utf8')
        self.assertNotIn('checked', content)
        self.assertContains(response, 'Pay now by debit card')

    def test_choice_must_be_made_before_proceeding(self):
        response = self.client.post(self.url)
        self.assertOnPage(response, 'choose_method')
        form = response.context['form']
        self.assertTrue(form.errors)


@patch_notifications()
@patch_gov_uk_pay_availability_check()
@override_settings(BANK_TRANSFERS_ENABLED=False)
class ChooseMethodViewTestCaseBankTransferDisabled(BaseTestCase):
    url = '/en-gb/'

    def test_shows_only_debit_card_payment_options(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')
        self.assertResponseNotCacheable(response)
        content = response.content.decode('utf8')
        self.assertIn('id_debit_card', content)
        self.assertNotIn('id_bank_transfer', content)

    def test_session_reset_if_returning_to_page(self):
        response = self.client.post(self.url, data={
            'payment_method': PaymentMethod.debit_card.name
        }, follow=True)
        self.assertOnPage(response, 'prisoner_details_debit')
        response = self.client.get(self.url, follow=True)
        content = response.content.decode('utf8')
        self.assertNotIn('checked', content)
        self.assertContains(response, 'Pay now by debit card')

    def test_choice_must_be_made_before_proceeding(self):
        response = self.client.post(self.url)
        self.assertOnPage(response, 'choose_method')
        form = response.context['form']
        self.assertTrue(form.errors)


# BANK TRANSFER FLOW

@patch_notifications()
@override_settings(
    BANK_TRANSFER_PRISONS='',
    DEBIT_CARD_PRISONS='',
    BANK_TRANSFERS_ENABLED=True
)
class BankTransferFlowTestCase(BaseTestCase):
    complete_session_keys = [
        'payment_method',
        'prisoner_number',
        'prisoner_dob',
    ]

    @classmethod
    def patch_prisoner_details_check(cls):
        return mock.patch('send_money.forms.BankTransferPrisonerDetailsForm.is_prisoner_known',
                          return_value=True)

    def choose_bank_transfer_payment_method(self, should_fail=False):
        response = self.client.post(self.root_url, data={
            'payment_method': PaymentMethod.bank_transfer.name
        }, follow=True)
        if not should_fail:
            self.assertOnPage(response, 'bank_transfer_warning')
        return response

    def fill_in_prisoner_details(self, **kwargs):
        data = {
            'prisoner_number': 'A1231DE',
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
        data.update(kwargs)
        with self.patch_prisoner_details_check():
            return self.client.post(BankTransferPrisonerDetailsTestCase.url, data=data, follow=True)


@patch_notifications()
@patch_gov_uk_pay_availability_check()
@override_settings(BANK_TRANSFERS_ENABLED=True)
class BankTransferWarningTestCase(BankTransferFlowTestCase):
    url = '/en-gb/bank-transfer/warning/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    def test_redirected_if_accessed_after_choosing_debit_card(self):
        self.client.post(self.root_url, data={
            'payment_method': PaymentMethod.debit_card.name
        }, follow=True)
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    @override_settings(BANK_TRANSFERS_ENABLED=False)
    def test_not_redirected_if_accessed_after_choosing_debit_card_if_bank_transfer_not_enabled(self):
        self.client.post(self.root_url, data={
            'payment_method': PaymentMethod.debit_card.name
        }, follow=True)
        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 404)
        self.assertIn(response.content, b'Bank Transfers are no longer supported by this service')

    def test_warning_page_shows(self):
        response = self.choose_bank_transfer_payment_method()
        self.assertOnPage(response, 'bank_transfer_warning')
        self.assertResponseNotCacheable(response)

    @override_settings(BANK_TRANSFERS_ENABLED=False)
    def test_warning_page_does_not_show_if_bank_transfer_not_enabled(self):
        response = self.choose_bank_transfer_payment_method(should_fail=True)
        self.assertOnPage(response, 'choose_method')


@patch_notifications()
@patch_gov_uk_pay_availability_check()
@override_settings(BANK_TRANSFERS_ENABLED=True)
class BankTransferPrisonerDetailsTestCase(BankTransferFlowTestCase):
    url = '/en-gb/bank-transfer/details/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    @override_settings(BANK_TRANSFERS_ENABLED=False)
    def test_cannot_access_if_bank_transfer_not_enabled(self):
        self.choose_bank_transfer_payment_method(should_fail=True)

        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 404)
        self.assertIn(response.content, b'Bank Transfers are no longer supported by this service')

    @override_settings(BANK_TRANSFERS_ENABLED=False)
    def test_cannot_submit_if_bank_transfer_not_enabled(self):
        self.choose_bank_transfer_payment_method(should_fail=True)

        with silence_logger():
            response = self.client.post(self.url, data={
                'prisoner_number': 'A1231DE',
                'prisoner_dob_0': '4',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }, follow=True)
            self.assertEqual(response.status_code, 404)
            self.assertIn(response.content, b'Bank Transfers are no longer supported by this service')

    def test_cannot_submit_if_continuing_from_session_and_bank_transfer_not_enabled(self):
        with override_settings(BANK_TRANSFERS_ENABLED=True):
            self.choose_bank_transfer_payment_method()

        with silence_logger() and override_settings(BANK_TRANSFERS_ENABLED=False):
            response = self.client.post(self.url, data={
                'prisoner_number': 'A1231DE',
                'prisoner_dob_0': '4',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }, follow=True)
            self.assertEqual(response.status_code, 404)
            self.assertIn(response.content, b'Bank Transfers are no longer supported by this service')

    def test_can_pass_warning_page(self):
        self.choose_bank_transfer_payment_method()

        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'prisoner_details_bank')
        self.assertResponseNotCacheable(response)

    def test_can_skip_back_to_payment_choice_page(self):
        self.choose_bank_transfer_payment_method()

        response = self.client.get(self.root_url, follow=True)
        self.assertOnPage(response, 'choose_method')

    @mock.patch('send_money.forms.BankTransferPrisonerDetailsForm.is_prisoner_known')
    def test_displays_errors_for_dropped_api_connection(self, mocked_is_prisoner_known):
        self.choose_bank_transfer_payment_method()

        mocked_is_prisoner_known.side_effect = ConnectionError
        with silence_logger():
            response = self.client.post(self.url, data={
                'prisoner_number': 'A1231DE',
                'prisoner_dob_0': '4',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }, follow=True)
        self.assertContains(response, 'This service is currently unavailable')
        form = response.context['form']
        self.assertTrue(form.errors)

    @mock.patch('send_money.forms.BankTransferPrisonerDetailsForm.is_prisoner_known')
    def test_empty_form_submission_shows_errors(self, mocked_is_prisoner_known):
        self.choose_bank_transfer_payment_method()

        response = self.client.post(self.url, follow=True)
        self.assertOnPage(response, 'prisoner_details_bank')
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertEqual(mocked_is_prisoner_known.call_count, 0)

    @mock.patch('send_money.forms.BankTransferPrisonerDetailsForm.is_prisoner_known')
    def test_displays_errors_for_invalid_prisoner_number(self, mocked_is_prisoner_known):
        self.choose_bank_transfer_payment_method()

        response = self.client.post(self.url, data={
            'prisoner_number': 'a1231a1',
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }, follow=True)
        self.assertContains(response, 'Incorrect prisoner number format')
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertEqual(mocked_is_prisoner_known.call_count, 0)

    @mock.patch('send_money.forms.BankTransferPrisonerDetailsForm.is_prisoner_known')
    def test_displays_errors_for_missing_prisoner_dob(self, mocked_is_prisoner_known):
        self.choose_bank_transfer_payment_method()

        response = self.client.post(self.url, data={
            'prisoner_number': 'A1231DE',
        }, follow=True)
        self.assertContains(response, 'This field is required')
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertEqual(mocked_is_prisoner_known.call_count, 0)

    @mock.patch('send_money.forms.BankTransferPrisonerDetailsForm.is_prisoner_known')
    def test_displays_errors_for_invalid_prisoner_details(self, mocked_is_prisoner_known):
        self.choose_bank_transfer_payment_method()

        mocked_is_prisoner_known.return_value = False
        response = self.client.post(self.url, data={
            'prisoner_number': 'A1231DE',
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }, follow=True)
        self.assertContains(response, 'No prisoner matches the details')
        form = response.context['form']
        self.assertTrue(form.errors)

    @override_settings(BANK_TRANSFER_PRISONS='')
    @mock.patch('send_money.forms.PrisonerDetailsForm.get_api_session')
    def test_search_not_limited_to_specific_prisons(self, mocked_api_session):
        mocked_api_session.side_effect = get_api_session
        self.choose_bank_transfer_payment_method()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/prisoner_validity/') + '?prisoner_number=A1231DE'
                                                 '&prisoner_dob=1980-10-04',
                match_querystring=True,
                json={
                    'count': 0,
                    'results': []
                },
            )
            self.client.post(self.url, data={
                'prisoner_number': 'A1231DE',
                'prisoner_dob_0': '4',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }, follow=True)

    @override_settings(BANK_TRANSFER_PRISONS='DEF,ABC')
    @mock.patch('send_money.forms.PrisonerDetailsForm.get_api_session')
    def test_can_limit_search_to_specific_prisons(self, mocked_api_session):
        mocked_api_session.side_effect = get_api_session
        self.choose_bank_transfer_payment_method()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/prisoner_validity/') + '?prisoner_number=A1231DE'
                                                 '&prisoner_dob=1980-10-04'
                                                 '&prisons=ABC,DEF',
                match_querystring=True,
                json={
                    'count': 0,
                    'results': []
                },
            )
            self.client.post(self.url, data={
                'prisoner_number': 'A1231DE',
                'prisoner_dob_0': '4',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }, follow=True)


@patch_notifications()
@patch_gov_uk_pay_availability_check()
@override_settings(BANK_TRANSFERS_ENABLED=True)
class BankTransferReferenceTestCase(BankTransferFlowTestCase):
    url = '/en-gb/bank-transfer/reference/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    def test_can_reach_reference_page(self):
        self.choose_bank_transfer_payment_method()

        response = self.fill_in_prisoner_details()
        self.assertOnPage(response, 'bank_transfer')
        self.assertResponseNotCacheable(response)

    @override_settings(BANK_TRANSFERS_ENABLED=False)
    def test_cannot_submit_if_bank_transfer_not_enabled(self):
        self.choose_bank_transfer_payment_method(should_fail=True)

        response = self.fill_in_prisoner_details()
        self.assertEqual(response.status_code, 404)
        self.assertIn(response.content, b'Bank Transfers are no longer supported by this service')

    def test_bank_transfer_page_clears_session_after_delay(self):
        with self.settings(CONFIRMATION_EXPIRES=0):
            self.choose_bank_transfer_payment_method()
            for key in ['payment_method']:
                self.assertIn(key, self.client.session)

            self.fill_in_prisoner_details()
            time.sleep(0.1)
            response = self.client.get(self.url, follow=True)
            for key in self.complete_session_keys:
                self.assertNotIn(key, self.client.session)
            self.assertOnPage(response, 'choose_method')

    @override_settings(NOMS_HOLDING_ACCOUNT_NAME='NOMS',
                       NOMS_HOLDING_ACCOUNT_NUMBER='1001001',
                       NOMS_HOLDING_ACCOUNT_SORT_CODE='10-20-30')
    def test_noms_account_details_presented_correctly(self):
        self.choose_bank_transfer_payment_method()

        response = self.fill_in_prisoner_details()
        expected_data = {
            'account_number': '1001001',
            'sort_code': '10-20-30',
        }
        for key, value in expected_data.items():
            self.assertContains(response, value)
            self.assertEqual(response.context[key], value)

    def test_reference_number_presented_correctly(self):
        self.choose_bank_transfer_payment_method()

        response = self.fill_in_prisoner_details()
        bank_transfer_reference = 'A1231DE/04/10/80'
        self.assertContains(response, bank_transfer_reference)
        self.assertEqual(response.context['bank_transfer_reference'], bank_transfer_reference)


# DEBIT CARD FLOW


@patch_notifications()
@override_settings(BANK_TRANSFER_PRISONS='',
                   DEBIT_CARD_PRISONS='')
class DebitCardFlowTestCase(BaseTestCase):
    complete_session_keys = [
        'payment_method',
        'prisoner_name',
        'prisoner_number',
        'prisoner_dob',
        'amount',
    ]
    prisoner_number = 'A1231DE'

    @classmethod
    def patch_prisoner_details_check(cls):
        return mock.patch('send_money.forms.DebitCardPrisonerDetailsForm.is_prisoner_known',
                          return_value=True)

    @classmethod
    def patch_prisoner_balance_check(cls):
        return mock.patch('send_money.forms.DebitCardAmountForm.is_account_balance_below_threshold',
                          return_value=True)

    def choose_debit_card_payment_method(self):
        response = self.client.post(self.root_url, data={
            'payment_method': PaymentMethod.debit_card.name
        }, follow=True)
        self.assertOnPage(response, 'prisoner_details_debit')

    def fill_in_prisoner_details(self, **kwargs):
        data = {
            'prisoner_name': 'John Smith',
            'prisoner_number': self.prisoner_number,
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
        data.update(kwargs)
        with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check():
            return self.client.post(DebitCardPrisonerDetailsTestCase.url, data=data, follow=True)

    def fill_in_amount(self, **kwargs):
        data = {
            'amount': '17'
        }
        data.update(kwargs)
        with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check():
            return self.client.post(DebitCardAmountTestCase.url, data=data, follow=True)


@patch_notifications()
@patch_gov_uk_pay_availability_check()
class DebitCardPrisonerDetailsTestCase(DebitCardFlowTestCase):
    url = '/en-gb/debit-card/details/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    def test_redirected_if_accessed_after_choosing_bank_transfer(self):
        self.client.post(self.root_url, data={
            'payment_method': PaymentMethod.bank_transfer.name
        }, follow=True)
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    @mock.patch('send_money.forms.DebitCardPrisonerDetailsForm.is_prisoner_known')
    def test_displays_errors_for_dropped_api_connection(self, mocked_is_prisoner_known):
        self.choose_debit_card_payment_method()

        mocked_is_prisoner_known.side_effect = ConnectionError
        with silence_logger():
            response = self.client.post(self.url, data={
                'prisoner_name': 'john smith',
                'prisoner_number': 'A1231DE',
                'prisoner_dob_0': '4',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            })
        self.assertContains(response, 'This service is currently unavailable')
        form = response.context['form']
        self.assertTrue(form.errors)

    @mock.patch('send_money.forms.DebitCardPrisonerDetailsForm.is_prisoner_known')
    def test_empty_form_submission_shows_errors(self, mocked_is_prisoner_known):
        self.choose_debit_card_payment_method()

        response = self.client.post(self.url, follow=True)
        self.assertOnPage(response, 'prisoner_details_debit')
        self.assertResponseNotCacheable(response)
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertEqual(mocked_is_prisoner_known.call_count, 0)

    @mock.patch('send_money.forms.DebitCardPrisonerDetailsForm.is_prisoner_known')
    def test_displays_errors_for_invalid_prisoner_number(self, mocked_is_prisoner_known):
        self.choose_debit_card_payment_method()

        response = self.client.post(self.url, data={
            'prisoner_name': 'john smith',
            'prisoner_number': 'a1231a1',
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        })
        self.assertContains(response, 'Incorrect prisoner number format')
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertEqual(mocked_is_prisoner_known.call_count, 0)

    @mock.patch('send_money.forms.DebitCardPrisonerDetailsForm.is_prisoner_known')
    def test_displays_errors_for_missing_prisoner_dob(self, mocked_is_prisoner_known):
        self.choose_debit_card_payment_method()

        response = self.client.post(self.url, data={
            'prisoner_name': 'john smith',
            'prisoner_number': 'A1231DE',
        })
        self.assertContains(response, 'This field is required')
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertEqual(mocked_is_prisoner_known.call_count, 0)

    @mock.patch('send_money.forms.DebitCardPrisonerDetailsForm.is_prisoner_known')
    def test_displays_errors_for_invalid_prisoner_details(self, mocked_is_prisoner_known):
        self.choose_debit_card_payment_method()

        mocked_is_prisoner_known.return_value = False
        response = self.client.post(self.url, data={
            'prisoner_name': 'john smith',
            'prisoner_number': 'A1231DE',
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        })
        self.assertContains(response, 'No prisoner matches the details')
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertEqual(mocked_is_prisoner_known.call_count, 1)

    @mock.patch('send_money.forms.DebitCardPrisonerDetailsForm.is_prisoner_known')
    def test_displays_errors_for_missing_name(self, mocked_is_prisoner_known):
        self.choose_debit_card_payment_method()

        mocked_is_prisoner_known.return_value = False
        response = self.client.post(self.url, data={
            'prisoner_number': 'A1231DE',
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        })
        self.assertContains(response, 'This field is required')
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertEqual(mocked_is_prisoner_known.call_count, 0)

    @override_settings(DEBIT_CARD_PRISONS='')
    @mock.patch('send_money.forms.PrisonerDetailsForm.get_api_session')
    def test_search_not_limited_to_specific_prisons(self, mocked_api_session):
        mocked_api_session.side_effect = get_api_session
        self.choose_debit_card_payment_method()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/prisoner_validity/') + '?prisoner_number=A1231DE'
                                                 '&prisoner_dob=1980-10-04',
                match_querystring=True,
                json={
                    'count': 0,
                    'results': []
                },
            )
            self.client.post(self.url, data={
                'prisoner_name': 'john smith',
                'prisoner_number': 'A1231DE',
                'prisoner_dob_0': '4',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }, follow=True)

    @override_settings(DEBIT_CARD_PRISONS='DEF,ABC,ZZZ')
    @mock.patch('send_money.forms.PrisonerDetailsForm.get_api_session')
    def test_can_limit_search_to_specific_prisons(self, mocked_api_session):
        mocked_api_session.side_effect = get_api_session
        self.choose_debit_card_payment_method()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/prisoner_validity/') + '?prisoner_number=A1231DE'
                                                 '&prisoner_dob=1980-10-04'
                                                 '&prisons=ABC,DEF,ZZZ',
                match_querystring=True,
                json={
                    'count': 0,
                    'results': []
                },
            )
            self.client.post(self.url, data={
                'prisoner_name': 'john smith',
                'prisoner_number': 'A1231DE',
                'prisoner_dob_0': '4',
                'prisoner_dob_1': '10',
                'prisoner_dob_2': '1980',
            }, follow=True)


@patch_notifications()
@patch_gov_uk_pay_availability_check()
class DebitCardAmountTestCase(DebitCardFlowTestCase):
    url = '/en-gb/debit-card/amount/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('0'),
                       SERVICE_CHARGE_FIXED=Decimal('0'))
    def test_send_money_page_shows_no_service_charge(self):
        self.choose_debit_card_payment_method()
        response = self.fill_in_prisoner_details()
        self.assertResponseNotCacheable(response)

        self.assertNotContains(response, 'mtp-charges-charges')  # an element class

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('2.5'),
                       SERVICE_CHARGE_FIXED=Decimal('0.21'))
    def test_send_money_page_shows_service_charge(self):
        self.choose_debit_card_payment_method()
        response = self.fill_in_prisoner_details()

        self.assertContains(response, '2.5%')
        self.assertContains(response, '21p')

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('0'),
                       SERVICE_CHARGE_FIXED=Decimal('0'))
    def test_empty_form_shows_errors(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()

        with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check():
            response = self.client.post(self.url, data={'amount': ''}, follow=True)
        self.assertOnPage(response, 'send_money_debit')
        form = response.context['form']
        self.assertTrue(form.errors)

    @override_settings(
        SERVICE_CHARGE_PERCENTAGE=Decimal('0'),
        SERVICE_CHARGE_FIXED=Decimal('0'),
        PRISONER_CAPPING_ENABLED=True,
        PRISONER_CAPPING_THRESHOLD_IN_POUNDS=Decimal('900')
    )
    @mock.patch('send_money.forms.DebitCardAmountForm.get_api_session', side_effect=lambda reconnect: get_api_session())
    def test_if_prisoner_cap_is_breached_error_displayed(self, mocked_api_session):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()

        with self.patch_prisoner_details_check(), responses.RequestsMock() as rsps:
            # This mock_auth(rsps) call needs to remain, as there appears to be an
            # issue where we need to call it in this test but not subsequent tests.
            # This probably means there is something wrong with the test setup or reset
            # to be investigated
            # The reason for this is due to the fact that `DebitCardAmountForm.get_api_session` binds
            # the session state to the class, and implements logic to not fetch it if it is set (and reconnect isn't
            # passed as an arg) This means that the auth call will only be made the first time
            # `DebitCardAmountForm.get_api_session` is invoked after `DebitCardAmountForm` is imported
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/prisoner_account_balances/{self.prisoner_number}'),
                json={
                    'combined_account_balance': 80001
                },
                status=200,
            )

            response = self.client.post(self.url, data={'amount': '100'}, follow=True)
            self.assertContains(response, 'It has reached its limit for now')
            form = response.context['form']
            self.assertTrue(form.errors)

    @override_settings(
        SERVICE_CHARGE_PERCENTAGE=Decimal('0'),
        SERVICE_CHARGE_FIXED=Decimal('0'),
        PRISONER_CAPPING_ENABLED=True,
        PRISONER_CAPPING_THRESHOLD_IN_POUNDS=Decimal('900')
    )
    @mock.patch('send_money.forms.DebitCardAmountForm.get_api_session', side_effect=lambda reconnect: get_api_session())
    def test_if_prisoner_cap_is_not_breached_when_prisoner_balance_will_be_900(self, mocked_api_session):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()

        with self.patch_prisoner_details_check(), responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/prisoner_account_balances/{self.prisoner_number}'),
                json={
                    'combined_account_balance': 80000
                },
                status=200,
            )

            response = self.client.post(self.url, data={'amount': '100'}, follow=True)
            self.assertOnPage(response, 'check_details')
            self.assertEqual(self.client.session.get('amount'), '100.00')

    @override_settings(
        SERVICE_CHARGE_PERCENTAGE=Decimal('0'),
        SERVICE_CHARGE_FIXED=Decimal('0'),
        PRISONER_CAPPING_ENABLED=True,
        PRISONER_CAPPING_THRESHOLD_IN_POUNDS=Decimal('900')
    )
    @mock.patch('send_money.forms.DebitCardAmountForm.get_api_session', side_effect=lambda reconnect: get_api_session())
    def test_if_prisoner_cap_is_not_breached_when_prisoner_balance_will_be_899_99(self, mocked_api_session):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()

        with self.patch_prisoner_details_check(), responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/prisoner_account_balances/{self.prisoner_number}'),
                json={
                    'combined_account_balance': 79999
                },
                status=200,
            )

            response = self.client.post(self.url, data={'amount': '100'}, follow=True)
            self.assertOnPage(response, 'check_details')
            self.assertEqual(self.client.session.get('amount'), '100.00')

    @override_settings(
        SERVICE_CHARGE_PERCENTAGE=Decimal('20'),
        SERVICE_CHARGE_FIXED=Decimal('50'),
        PRISONER_CAPPING_ENABLED=True,
        PRISONER_CAPPING_THRESHOLD_IN_POUNDS=Decimal('900')
    )
    @mock.patch('send_money.forms.DebitCardAmountForm.get_api_session', side_effect=lambda reconnect: get_api_session())
    def test_prisoner_cap_is_calculated_without_including_service_charge(self, mocked_api_session):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()

        with self.patch_prisoner_details_check(), responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/prisoner_account_balances/{self.prisoner_number}'),
                json={
                    'combined_account_balance': 80000
                },
                status=200,
            )

            response = self.client.post(self.url, data={'amount': '100'}, follow=True)
            self.assertOnPage(response, 'check_details')
            self.assertEqual(self.client.session.get('amount'), '100.00')

    @override_settings(
        PRISONER_CAPPING_ENABLED=False,
        PRISONER_CAPPING_THRESHOLD_IN_POUNDS=Decimal('50')
    )
    def test_amount_form_works_when_prisoner_capping_disabled(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()

        with self.patch_prisoner_details_check():
            response = self.client.post(self.url, data={'amount': '100'}, follow=True)
            self.assertOnPage(response, 'check_details')
            self.assertEqual(self.client.session.get('amount'), '100.00')

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('0'),
                       SERVICE_CHARGE_FIXED=Decimal('0'))
    def test_amount_saved_and_can_be_changed(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()

        with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check():
            response = self.client.post(self.url, data={'amount': '50'}, follow=True)
            self.assertOnPage(response, 'check_details')
            self.assertEqual(self.client.session.get('amount'), '50.00')
            response = self.client.get(self.url)
            self.assertContains(response, '"50.00"')
            response = self.client.post(self.url, data={'amount': '55.50'}, follow=True)
            self.assertOnPage(response, 'check_details')
            self.assertEqual(self.client.session.get('amount'), '55.50')


@patch_notifications()
@patch_gov_uk_pay_availability_check()
class DebitCardCheckTestCase(DebitCardFlowTestCase):
    url = '/en-gb/debit-card/check/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('2'),
                       SERVICE_CHARGE_FIXED=Decimal('1.21'))
    def test_check_page_displays_all_details(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        response = self.fill_in_amount()
        self.assertResponseNotCacheable(response)

        content = response.content.decode('utf8')
        self.assertIn('John Smith', content)
        self.assertIn('A1231DE', content)
        self.assertIn('4', content)
        self.assertIn('10', content)
        self.assertIn('1980', content)
        self.assertIn('£17', content)
        self.assertIn('£18.55', content)


@patch_notifications()
@patch_gov_uk_pay_availability_check()
@override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('2.4'),
                   SERVICE_CHARGE_FIXED=Decimal('0.20'),
                   GOVUK_PAY_URL='https://pay.gov.local/v1')
class DebitCardPaymentTestCase(DebitCardFlowTestCase):
    url = '/en-gb/debit-card/payment/'
    payment_process_path = '/take'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    def test_debit_card_payment(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            ref = 'wargle-blargle'
            processor_id = '3'
            mock_auth(rsps)
            rsps.add(
                rsps.POST,
                api_url('/payments/'),
                json={'uuid': ref},
                status=201,
            )
            rsps.add(
                rsps.POST,
                govuk_url('/payments/'),
                json={
                    'payment_id': processor_id,
                    '_links': {
                        'next_url': {
                            'method': 'GET',
                            'href': govuk_url(self.payment_process_path),
                        }
                    }
                },
                status=201,
            )
            rsps.add(
                rsps.PATCH,
                api_url('/payments/%s/' % ref),
                json={
                    'uuid': ref,
                    'processor_id': processor_id,
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check():
                response = self.client.get(self.url, follow=False)

            # check amount and service charge submitted to api
            payment_request = json.loads(rsps.calls[1].request.body.decode('utf8'))
            self.assertEqual(payment_request['amount'], 1700)
            self.assertEqual(payment_request['service_charge'], 61)
            self.assertEqual(payment_request['ip_address'], None)  # only forwarded-for IP is recorded

            # check total charge submitted to govuk
            govuk_request = json.loads(rsps.calls[2].request.body.decode('utf8'))
            self.assertEqual(govuk_request['amount'], 1761)

            self.assertRedirects(
                response, govuk_url(self.payment_process_path),
                fetch_redirect_response=False
            )

    @mock.patch('send_money.views.should_be_capture_delayed', mock.Mock(return_value=True))
    def test_debit_card_payment_with_delayed_capture(self):
        """
        Test that if the payment should have delayed capture, the view calls the GOV.UK API
        create payment endpoint with delayed_capture == True.
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            ref = 'wargle-blargle'
            processor_id = '3'
            mock_auth(rsps)
            rsps.add(
                rsps.POST,
                api_url('/payments/'),
                json={'uuid': ref},
                status=201,
            )
            rsps.add(
                rsps.POST,
                govuk_url('/payments/'),
                json={
                    'payment_id': processor_id,
                    '_links': {
                        'next_url': {
                            'method': 'GET',
                            'href': govuk_url(self.payment_process_path),
                        }
                    }
                },
                status=201
            )
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{ref}/'),
                json={
                    'uuid': ref,
                    'processor_id': processor_id,
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger(level=logging.WARNING):  # noqa: E501
                response = self.client.get(self.url, follow=False)

            # check delayed param in govuk pay call
            govuk_request = json.loads(rsps.calls[2].request.body.decode('utf8'))
            self.assertEqual(govuk_request['delayed_capture'], True)

            self.assertRedirects(
                response, govuk_url(self.payment_process_path),
                fetch_redirect_response=False
            )

    def test_debit_card_payment_handles_api_errors(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.POST,
                api_url('/payments/'),
                status=500,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(self.url, follow=False)
            self.assertContains(response, 'We are experiencing technical problems')

    def test_debit_card_payment_handles_govuk_errors(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.POST,
                api_url('/payments/'),
                json={'uuid': 'wargle-blargle'},
                status=201,
            )
            rsps.add(
                rsps.POST,
                govuk_url('/payments/'),
                status=500
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(self.url, follow=False)
            self.assertContains(response, 'We are experiencing technical problems')


@patch_notifications()
@patch_gov_uk_pay_availability_check()
@override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('2.4'),
                   SERVICE_CHARGE_FIXED=Decimal('0.20'),
                   GOVUK_PAY_URL='https://pay.gov.local/v1')
class DebitCardConfirmationTestCase(DebitCardFlowTestCase):
    url = '/en-gb/debit-card/confirmation/'
    ref = 'wargle-blargle'
    processor_id = '3'
    payment_data = {
        'uuid': ref,
        'processor_id': processor_id,
        'recipient_name': 'John',
        'amount': 1700,
        'status': 'pending',
        'created': datetime.datetime.now().isoformat() + 'Z',
        'modified': datetime.datetime.now().isoformat() + 'Z',
        'received_at': datetime.datetime.now().isoformat() + 'Z',
        'prisoner_number': 'A1409AE',
        'prisoner_dob': '1989-01-21',
    }

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    def test_redirects_if_no_reference_param(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check():
            response = self.client.get(self.url, data={'payment_ref': ''}, follow=True)
        self.assertOnPage(response, 'choose_method')

    @mock.patch('send_money.payments.PaymentClient.api_session')
    def test_escapes_reference_param(self, mocked_api_session):
        from mtp_common.auth.exceptions import HttpNotFoundError

        mocked_api_session.get.side_effect = HttpNotFoundError

        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check():
            self.client.get(self.url, data={'payment_ref': '../service-availability/'})
        mocked_api_session.get.assert_called_with('/payments/..%2Fservice-availability%2F/')

    @override_settings(ENVIRONMENT='prod')  # because non-prod environments don't send to @outside.local
    def test_success_confirmation(self):
        """
        Test that if the GOV.UK payment is in status 'success', the view:
        - updates the MTP payment record with the email address provided by GOV.UK Pay
        - shows a confirmation page
        - no email is sent (the confirmation email is sent when we get the capture date)
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'reference': self.ref,
                    'state': {'status': 'success'},
                    'email': 'sender@outside.local',
                    'settlement_summary': {
                        'capture_submit_time': None,
                        'captured_date': None,
                    },
                },
                status=200
            )
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{self.ref}/'),
                json={
                    **self.payment_data,
                    'email': 'sender@outside.local',
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=False,
                )
        self.assertContains(response, 'success')
        self.assertResponseNotCacheable(response)

        # check session is cleared
        for key in self.complete_session_keys:
            self.assertNotIn(key, self.client.session)

        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ENVIRONMENT='prod')  # because non-prod environments don't send to @outside.local
    def test_automatically_captures_payment(self):
        """
        Test that if the GOV.UK payment is in status 'capturable' and the payment should be
        automatically captured, the view:
        - updates the MTP payment record with the email address and other details provided by GOV.UK Pay
        - captures the payment
        - shows a confirmation page
        - no email is sent (the confirmation email is sent when we get the capture date)
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'payment_id': self.processor_id,
                    'reference': self.ref,
                    'state': {'status': 'capturable'},
                    'email': 'sender@outside.local',
                    'settlement_summary': {
                        'capture_submit_time': None,
                        'captured_date': None,
                    },
                },
                status=200,
            )
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{self.ref}/'),
                json={
                    **self.payment_data,
                    'email': 'sender@outside.local',
                    'security_check': {
                        'status': 'accepted',
                        'user_actioned': False,
                    },
                },
                status=200,
            )
            rsps.add(
                rsps.POST,
                govuk_url(f'/payments/{self.processor_id}/capture/'),
                status=204,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=False,
                )
        self.assertContains(response, 'success')
        self.assertResponseNotCacheable(response)

        # check session is cleared
        for key in self.complete_session_keys:
            self.assertNotIn(key, self.client.session)

        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ENVIRONMENT='prod')  # because non-prod environments don't send to @outside.local
    def test_puts_payment_on_hold(self):
        """
        Test that if the GOV.UK payment is in status 'capturable' and the payment should not be captured, the view:
        - updates the MTP payment record with the email address and other details provided by GOV.UK Pay
        - sends a email saying that the payment is on hold
        - shows a page saying that the payment in on hold
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'payment_id': self.processor_id,
                    'reference': self.ref,
                    'state': {'status': 'capturable'},
                    'email': 'sender@outside.local',
                    'settlement_summary': {
                        'capture_submit_time': None,
                        'captured_date': None,
                    },
                },
                status=200,
            )
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{self.ref}/'),
                json={
                    **self.payment_data,
                    'email': 'sender@outside.local',
                    'security_check': {
                        'status': 'pending',
                        'user_actioned': False,
                    },
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=False,
                )
        self.assertContains(response, 'being processed')
        self.assertNotContains(response, 'on hold')
        self.assertResponseNotCacheable(response)

        # check session is cleared
        for key in self.complete_session_keys:
            self.assertNotIn(key, self.client.session)

        self.assertEqual('Send money to someone in prison: your payment is being processed', mail.outbox[0].subject)
        self.assertTrue('WARGLE-B' in mail.outbox[0].body)
        self.assertTrue('£17' in mail.outbox[0].body)

    def assertOnPaymentDeclinedPage(self, response):  # noqa: N802
        """
        Payment was declined by card issuer or WorldPay (e.g. due to insufficient funds or risk management)
        - card declined page presented
        - no emails sent
        - session remains
        """
        self.assertContains(response, 'Your payment has been declined')
        self.assertEqual(response.templates[0].name, 'send_money/debit-card-declined.html')

        self.assertEqual(len(mail.outbox), 0)

        for key in self.complete_session_keys:
            self.assertIn(key, self.client.session)

    def assertOnPaymentCancelledPage(self, response):  # noqa: N802
        """
        Payment was cancelled by user or through GOV.UK Pay api
        - payment cancelled page presented
        - no emails sent
        - session remains
        """
        self.assertContains(response, 'Your payment has been cancelled')
        self.assertEqual(response.templates[0].name, 'send_money/debit-card-cancelled.html')

        self.assertEqual(len(mail.outbox), 0)

        for key in self.complete_session_keys:
            self.assertIn(key, self.client.session)

    def assertOnPaymentSessionExpiredPage(self, response):  # noqa: N802
        """
        User did not complete forms in GOV.UK Pay in allowed time
        - payment session expired page presented
        - no emails sent
        - session remains
        """
        self.assertContains(response, 'Your payment session has expired')
        self.assertEqual(response.templates[0].name, 'send_money/debit-card-session-expired.html')

        self.assertEqual(len(mail.outbox), 0)

        for key in self.complete_session_keys:
            self.assertIn(key, self.client.session)

    def assertOnPaymentErrorPage(self, response):  # noqa: N802
        """
        An unexpected error occurred communicating with mtp-api, GOV.UK Pay or GOV.UK Pay returned an explicit error
        - payment error page presented with reference
        - no emails sent
        - session cleared
        """
        self.assertContains(response, 'We are experiencing technical problems')
        self.assertContains(response, self.ref[:8].upper())

        self.assertEqual(len(mail.outbox), 0)

        for key in self.complete_session_keys:
            self.assertNotIn(key, self.client.session)

    def test_handles_api_update_errors(self):
        """
        Test that if the MTP API call returns 500, the view shows a generic error page
        and no email is sent.
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                status=500,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=False,
                )

        self.assertOnPaymentErrorPage(response)

    def test_handles_govuk_errors(self):
        """
        Test that if the GOV.UK API call returns 500, the view shows a generic error page
        and no email is sent.
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                status=500
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=False,
                )

        self.assertOnPaymentErrorPage(response)

    def test_handles_missing_govuk_payment(self):
        """
        Test that if the GOV.UK API call returns 404, the view shows a generic error page
        and no email is sent; even though MTP payment exists.
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                status=404,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=True,
                )

        self.assertOnPaymentErrorPage(response)

    def test_handles_unexpected_govuk_response(self):
        """
        Test that if the GOV.UK API call returns unexpected status, the view shows a generic error page
        and no email is sent.
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'reference': self.ref,
                    'state': {'status': 'UNEXPECTED', 'code': 'P9090'},
                    'email': 'sender@outside.local',
                },
                status=200
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=True,
                )

        self.assertOnPaymentErrorPage(response)

    def test_handles_declined_card(self):
        """
        Test that if the GOV.UK payment is in status 'failed' (P0010 e.g. because the card has insufficient funds),
        an error page is shown (since GOV.UK Pay now defers error display to this service).
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'reference': self.ref,
                    'state': {'status': 'failed', 'code': 'P0010'},
                    'email': 'sender@outside.local',
                },
                status=200
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=True,
                )

        self.assertOnPaymentDeclinedPage(response)

    def test_handles_payments_in_error(self):
        """
        Test that if the GOV.UK payment is in status 'error' (P0050 e.g. GOV.UK Pay could not contact WorldPay)
        an error page is shown (since GOV.UK Pay now defers error display to this service).
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'reference': self.ref,
                    'state': {
                        'status': 'error',
                        'code': 'P0050',
                        'message': 'Payment provider returned an error',
                    },
                    'payment_id': 12345,
                    'email': 'sender@outside.local',
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), mock.patch('send_money.payments.logger') as logger:  # noqa: E501
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=True,
                )
                error_log = logger.error.call_args[0][0]
                self.assertIn('12345', error_log)
                self.assertIn('P0050', error_log)

        self.assertOnPaymentErrorPage(response)

    def test_handles_payments_cancelled_by_us(self):
        """
        Test that if the GOV.UK payment is in status 'cancelled' (P0040) because we cancelled it
        (if the user cancels the payment, the actual GOV.UK status is 'failed')
        a cancelled page is shown (since GOV.UK Pay now defers error display to this service).

        NOTE: this never happens at the moment but it could with the introduction of delayed
        capture and it might need to change.
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'reference': self.ref,
                    'state': {'status': 'cancelled', 'code': 'P0040'},
                    'email': 'sender@outside.local',
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=True,
                )

        self.assertOnPaymentCancelledPage(response)

    def test_handles_payments_cancelled_by_user(self):
        """
        Test that if the GOV.UK payment is in status 'failed' (P0030) because the user cancelled it deliberately
        a cancelled page is shown (since GOV.UK Pay now defers error display to this service).
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'reference': self.ref,
                    'state': {'status': 'failed', 'code': 'P0030'},
                    'email': 'sender@outside.local',
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=True,
                )

        self.assertOnPaymentCancelledPage(response)

    def test_handles_payments_with_expired_session(self):
        """
        Test that if the GOV.UK payment is in status 'failed' (P0020) because the session expired
        (if the user took too long on GOV.UK Pay forms)
        a session-expired page is shown (since GOV.UK Pay now defers error display to this service).
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'reference': self.ref,
                    'state': {'status': 'failed', 'code': 'P0020'},
                    'email': 'sender@outside.local',
                },
                status=200
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=True,
                )

        self.assertOnPaymentSessionExpiredPage(response)

    def test_handles_payments_with_unusual_failed_code(self):
        """
        A `failed` status with P0020 or P0030 are treated as special.
        All others (including the very common P0010) should be treated equally.
        Similar to DebitCardConfirmationTestCase.test_handles_declined_card
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'reference': self.ref,
                    'state': {'status': 'failed', 'code': 'P990099'},
                    'email': 'sender@outside.local',
                },
                status=200
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), mock.patch('send_money.views.logger') as logger:  # noqa: E501
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=True,
                )
                error_log = logger.error.call_args[0][0]
                self.assertIn(self.ref, error_log)
                self.assertIn('failed', error_log)
                self.assertIn('P990099', error_log)

        self.assertOnPaymentDeclinedPage(response)

    def test_handles_payments_with_unusual_cancelled_code(self):
        """
        A `cancelled` status expects a P0040 code, but we should treat all cancellations equally.
        Similar to DebitCardConfirmationTestCase.test_handles_payments_cancelled_by_us
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'reference': self.ref,
                    'state': {'status': 'cancelled', 'code': 'P990099'},
                    'email': 'sender@outside.local',
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), mock.patch('send_money.views.logger') as logger:  # noqa: E501
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=True,
                )
                error_log = logger.error.call_args[0][0]
                self.assertIn(self.ref, error_log)
                self.assertIn('cancelled', error_log)
                self.assertIn('P990099', error_log)

        self.assertOnPaymentCancelledPage(response)

    def test_handles_payments_with_unusual_error_code(self):
        """
        An `error` status with P0050 code is common, but we should treat all errors equally.
        Similar to DebitCardConfirmationTestCase.test_handles_payments_in_error
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json=self.payment_data,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{self.processor_id}/'),
                json={
                    'reference': self.ref,
                    'state': {'status': 'error'},
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), mock.patch('send_money.payments.logger') as logger:  # noqa: E501
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=True,
                )
                error_log = logger.error.call_args[0][0]
                self.assertIn(self.ref, error_log)
                self.assertIn('None', error_log)

        self.assertOnPaymentErrorPage(response)

    def test_refreshes_for_recently_completed_payments(self):
        """
        Test that if the user refreshes the page after the MTP payment was moved to the 'taken' status
        by the cronjob x mins after the GOV.UK payment succeeded, the user sees a success confirmation
        page and no email is sent.
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json={
                    **self.payment_data,
                    'status': 'taken',
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=False,
                )

        self.assertContains(response, 'success')
        # check no new email sent
        self.assertEqual(len(mail.outbox), 0)

    def test_redirects_for_old_payments(self):
        """
        Test that if the user refreshes the page a long time after the MTP payment was moved to the 'taken' status
        by the cronjob x mins after the GOV.UK payment succeeded, the user is redirected to the
        start of the journey.
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        payment_time = (
            datetime.datetime.now() - datetime.timedelta(hours=2)
        ).isoformat() + 'Z'

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json={
                    **self.payment_data,

                    'status': 'taken',
                    'created': payment_time,
                    'received_at': payment_time,
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=False,
                )
            self.assertRedirects(response, '/en-gb/', fetch_redirect_response=False)

    def test_redirects_for_old_failed_payments(self):
        """
        Test that if the user click on the 'Continue' button on GOV.UK Pay to return to
        our service a long time after it failed, the view redirects to the start of the
        journey as Pay has already shown an error page.
        """
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        payment_time = (
            datetime.datetime.now() - datetime.timedelta(hours=2)
        ).isoformat() + 'Z'

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{self.ref}/'),
                json={
                    **self.payment_data,

                    'status': 'failed',
                    'created': payment_time,
                    'received_at': None,
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check(), silence_logger():
                response = self.client.get(
                    self.url,
                    {'payment_ref': self.ref},
                    follow=False,
                )
            self.assertRedirects(response, '/en-gb/', fetch_redirect_response=False)


@patch_notifications()
@mock.patch(
    'send_money.forms.check_payment_service_available',
    mock.Mock(return_value=(False, 'Scheduled work message')),
)
@override_settings(BANK_TRANSFERS_ENABLED=True)
class PaymentServiceUnavailableTestCase(DebitCardFlowTestCase):
    choose_method_url = '/en-gb/'

    def test_gov_uk_service_unavailable_hides_debit_card_route(self):
        response = self.client.get(self.choose_method_url, follow=True)
        self.assertNotContains(response, 'id_debit_card')
        self.assertContains(response, 'id_bank_transfer')

    def test_gov_uk_service_unavailable_can_show_message_to_users(self):
        response = self.client.get(self.choose_method_url, follow=True)
        self.assertContains(response, 'Scheduled work message')

    def test_gov_uk_service_unavailable_always_goes_to_bank_transfer(self):
        # no post data
        response = self.client.post(self.choose_method_url, follow=True)
        self.assertOnPage(response, 'bank_transfer_warning')

        # debit card chosen
        self.client.post(self.choose_method_url, data={
            'payment_method': PaymentMethod.debit_card.name
        }, follow=True)
        self.assertOnPage(response, 'bank_transfer_warning')

    @override_settings(
        ENVIRONMENT='prod',  # because non-prod environments don't send to @outside.local
        GOVUK_PAY_URL='https://pay.gov.local/v1',
    )
    def test_payment_can_complete_if_started_before_debit_card_payment_is_disabled(self):
        """
        Test that if a debit card payment starts before the card payment option is disabled,
        the system allows the user to complete the payment whilst stopping new payments from starting.
        """
        payment_ref = 'wargle-blargle'
        processor_id = '3'

        # make debit card available only for the first form to simulate the start of the payment process
        # before this payment option is turned off
        with mock.patch(
            'send_money.forms.check_payment_service_available',
            mock.Mock(
                return_value=(True, None),
            ),
        ):
            self.choose_debit_card_payment_method()

        self.fill_in_prisoner_details()
        self.fill_in_amount()

        payment = {
            'uuid': payment_ref,
            'processor_id': processor_id,
            'recipient_name': 'John',
            'amount': 1700,
            'status': 'pending',
            'created': f'{datetime.datetime.now().isoformat()}Z',
            'modified': f'{datetime.datetime.now().isoformat()}Z',
            'received_at': f'{datetime.datetime.now().isoformat()}Z',
            'prisoner_number': 'A1409AE',
            'prisoner_dob': '1989-01-21',
        }

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url(f'/payments/{payment_ref}/'),
                json=payment,
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url(f'/payments/{processor_id}/'),
                json={
                    'reference': payment_ref,
                    'state': {'status': 'success'},
                    'email': 'sender@outside.local',
                    'settlement_summary': {
                        'capture_submit_time': None,
                        'captured_date': None,
                    },
                },
                status=200,
            )
            rsps.add(
                rsps.PATCH,
                api_url(f'/payments/{payment_ref}/'),
                json={
                    **payment,
                    'email': 'sender@outside.local',
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.patch_prisoner_balance_check():
                response = self.client.get(
                    reverse('send_money:confirmation'),
                    {'payment_ref': payment_ref},
                    follow=False,
                )
            self.assertContains(response, 'success')


class ShouldBeCaptureDelayed(SimpleTestCase):
    """
    Tests related to the should_be_capture_delayed function.

    Note: the tests try a few times to exclude any randomness.
    """

    @override_settings(PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE='0')
    def test_false_if_0(self):
        """
        Test that if settings.PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE == 0, the
        method always returns False.
        """
        for _ in range(10):
            self.assertEqual(
                should_be_capture_delayed(),
                False,
            )

    @override_settings(PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE='100')
    def test_true_if_100(self):
        """
        Test that if settings.PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE == 100, the
        method always returns True.
        """
        for _ in range(10):
            self.assertEqual(
                should_be_capture_delayed(),
                True,
            )

    @override_settings(PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE='invalid')
    def test_invalid_value_disables_delay(self):
        """
        Test that if settings.PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE == invalid value,
        the method always returns False.
        """
        with self.assertLogs('mtp', level='ERROR') as cm:
            self.assertEqual(
                should_be_capture_delayed(),
                False,
            )

        self.assertEqual(
            cm.output,
            [
                'ERROR:mtp:PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE should be a number between 0 and 100, '
                'found invalid instead. Disabling delayed capture for now.'
            ]
        )

    @override_settings(PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE='-1')
    def test_negative_value_disables_delay(self):
        """
        Test that if settings.PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE == -1,
        the method always returns False.
        """
        with self.assertLogs('mtp', level='ERROR') as cm:
            self.assertEqual(
                should_be_capture_delayed(),
                False,
            )

        self.assertEqual(
            cm.output,
            [
                'ERROR:mtp:PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE should be a number between 0 and 100, '
                'found -1 instead. Disabling delayed capture for now.'
            ]
        )

    @override_settings(PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE='101')
    def test_too_big_value_disables_delay(self):
        """
        Test that if settings.PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE == 101,
        the method always returns False.
        """
        with self.assertLogs('mtp', level='ERROR') as cm:
            self.assertEqual(
                should_be_capture_delayed(),
                False,
            )

        self.assertEqual(
            cm.output,
            [
                'ERROR:mtp:PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE should be a number between 0 and 100, '
                'found 101 instead. Disabling delayed capture for now.'
            ]
        )

    @override_settings(PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE='50')
    def test_chance(self):
        """
        Test that if settings.PAYMENT_DELAYED_CAPTURE_ROLLOUT_PERCENTAGE == 50,
        the method returns True about 50% of the time.
        """
        chance = {
            True: 0,
            False: 0,
        }
        for _ in range(100):
            chance[should_be_capture_delayed()] += 1

        # we can't accurately check the figures
        self.assertTrue(chance[True] > 0)
        self.assertTrue(chance[False] > 0)
