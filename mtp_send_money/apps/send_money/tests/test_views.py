import datetime
import json
from contextlib import contextmanager
import logging
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import override_settings
from django.test.testcases import SimpleTestCase
from requests import ConnectionError
import responses

from send_money.models import PaymentMethod
from send_money.tests import mock_auth, patch_gov_uk_pay_availability_check
from send_money.utils import api_url, govuk_url


class BaseTestCase(SimpleTestCase):
    root_url = '/'

    @contextmanager
    def silence_logger(self, name='mtp', level=logging.CRITICAL):
        logger = logging.getLogger(name)
        old_level = logger.level
        logger.setLevel(level)
        yield
        logger.setLevel(old_level)

    def assertOnPage(self, response, url_name):  # noqa
        self.assertContains(response, '<!-- %s -->' % url_name)


class PaymentOptionAvailabilityTestCase(BaseTestCase):
    def assertPageNotFound(self, url):  # noqa
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404, msg='should not be able to access %s' % url)

    @override_settings(SHOW_BANK_TRANSFER_OPTION=False,
                       SHOW_DEBIT_CARD_OPTION=False)
    def test_payment_pages_inaccessible_when_no_options_enabled(self):
        with self.silence_logger('django.request'):
            self.assertPageNotFound('/bank-transfer/')
            self.assertPageNotFound('/bank-transfer/warning/')
            self.assertPageNotFound('/bank-transfer/details/')
            self.assertPageNotFound('/bank-transfer/reference/')
            self.assertPageNotFound('/debit-card/')
            self.assertPageNotFound('/debit-card/details/')
            self.assertPageNotFound('/debit-card/amount/')
            self.assertPageNotFound('/debit-card/check/')
            self.assertPageNotFound('/debit-card/payment/')
            self.assertPageNotFound('/debit-card/confirmation/')

    @override_settings(SHOW_BANK_TRANSFER_OPTION=False,
                       SHOW_DEBIT_CARD_OPTION=False)
    def test_root_page_redirects_when_no_options_enabled(self):
        response = self.client.get(self.root_url, follow=True)
        self.assertOnPage(response, 'submit_ticket')

    @override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                       SHOW_DEBIT_CARD_OPTION=False)
    def test_bank_transfer_flow_accessible_when_enabled(self):
        response = self.client.get(self.root_url, follow=True)
        self.assertOnPage(response, 'bank_transfer_warning')
        self.assertNotContains(response, 'Prisoner name')
        self.assertNotContains(response, 'Amount')

    @override_settings(SHOW_BANK_TRANSFER_OPTION=False,
                       SHOW_DEBIT_CARD_OPTION=True)
    def test_debit_card_flow_accessible_when_enabled(self):
        response = self.client.get(self.root_url, follow=True)
        self.assertOnPage(response, 'prisoner_details_debit')
        self.assertContains(response, 'Prisoner name')
        self.assertNotContains(response, 'Amount')

    @patch_gov_uk_pay_availability_check()
    @override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                       SHOW_DEBIT_CARD_OPTION=True)
    def test_both_flows_accessible_when_enabled(self):
        response = self.client.get(self.root_url, follow=True)
        self.assertOnPage(response, 'choose_method')
        self.assertNotContains(response, 'Prisoner name')
        self.assertNotContains(response, 'Amount')


@patch_gov_uk_pay_availability_check()
class ChooseMethodViewTestCase(BaseTestCase):
    url = '/'

    @override_settings(SHOW_BANK_TRANSFER_OPTION=False,
                       SHOW_DEBIT_CARD_OPTION=False)
    def test_redirects_to_feedback_if_both_flows_off(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'submit_ticket')

    @override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                       SHOW_DEBIT_CARD_OPTION=False)
    def test_redirects_to_bank_transfer_if_only_method(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'bank_transfer_warning')

    @override_settings(SHOW_BANK_TRANSFER_OPTION=False,
                       SHOW_DEBIT_CARD_OPTION=True)
    def test_redirects_to_debit_card_if_only_method(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'prisoner_details_debit')

    @override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                       SHOW_DEBIT_CARD_OPTION=True)
    def test_shows_all_payment_options(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')
        content = response.content.decode('utf8')
        for method in PaymentMethod:
            self.assertIn('id_%s' % method.name, content)
            self.assertIn(str(method.value), content)
        self.assertNotIn('checked', content)

    @override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                       SHOW_DEBIT_CARD_OPTION=True,
                       ENABLE_PAYMENT_CHOICE_EXPERIMENT=False)
    def test_option_preselected_if_returning_to_page(self):
        response = self.client.post(self.url, data={
            'payment_method': PaymentMethod.debit_card.name
        }, follow=True)
        self.assertOnPage(response, 'prisoner_details_debit')
        response = self.client.get(self.url, follow=True)
        content = response.content.decode('utf8')
        self.assertIn('checked', content)
        # when experiment is off, the bank transfer is the second option so 'checked' must come first
        self.assertLess(content.index('checked'),
                        content.index('id_%s' % PaymentMethod.bank_transfer.name))

    @override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                       SHOW_DEBIT_CARD_OPTION=True)
    def test_choice_must_be_made_before_proceeding(self):
        response = self.client.post(self.url)
        self.assertOnPage(response, 'choose_method')
        form = response.context['form']
        self.assertTrue(form.errors)

    @override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                       SHOW_DEBIT_CARD_OPTION=True,
                       ENABLE_PAYMENT_CHOICE_EXPERIMENT=False)
    def test_experiment_turns_off(self):
        from send_money.views import PaymentMethodChoiceView

        response = self.client.get(self.url)
        variation = response.cookies.get(PaymentMethodChoiceView.experiment_cookie_name)
        self.assertIsNone(variation)
        content = response.content.decode(response.charset)
        self.assertLess(content.find('id_debit_card'),
                        content.find('id_bank_transfer'),
                        'Debit card option should appear first according to experiment')

    @override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                       SHOW_DEBIT_CARD_OPTION=True,
                       ENABLE_PAYMENT_CHOICE_EXPERIMENT=True)
    def test_experiment_choice_cookie_and_ordering(self):
        from send_money.views import PaymentMethodChoiceView

        response = self.client.get(self.url)
        variation = response.cookies.get(PaymentMethodChoiceView.experiment_cookie_name)
        if variation:
            variation = variation.value
        self.assertTrue(variation, 'Cookie not saved')

        content = response.content.decode(response.charset)
        if variation == 'debit-card':
            self.assertLess(content.find('id_debit_card'),
                            content.find('id_bank_transfer'),
                            'Debit card option should appear first according to experiment')
        else:
            self.assertLess(content.find('id_bank_transfer'),
                            content.find('id_debit_card'),
                            'Bank transfer option should appear first according to experiment')


@mock.patch('send_money.forms.check_payment_service_available', mock.Mock(return_value=False))
class PaymentServiceUnavailableChooseMethodViewTestCase(BaseTestCase):
    url = '/'

    @override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                       SHOW_DEBIT_CARD_OPTION=True)
    def test_gov_uk_service_unavailable_disables_choice(self):
        response = self.client.get(self.url, follow=True)
        self.assertContains(response, 'disabled')

    @override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                       SHOW_DEBIT_CARD_OPTION=True)
    def test_gov_uk_service_unavailable_always_goes_to_bank_transfer(self):
        # no post data
        response = self.client.post(self.url, follow=True)
        self.assertOnPage(response, 'bank_transfer_warning')

        # debit card chosen
        self.client.post(self.root_url, data={
            'payment_method': PaymentMethod.debit_card.name
        }, follow=True)
        self.assertOnPage(response, 'bank_transfer_warning')


# BANK TRANSFER FLOW


@override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                   SHOW_DEBIT_CARD_OPTION=True,
                   BANK_TRANSFER_PRISONS='',
                   DEBIT_CARD_PRISONS='')
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

    def choose_bank_transfer_payment_method(self):
        return self.client.post(self.root_url, data={
            'payment_method': PaymentMethod.bank_transfer.name
        }, follow=True)

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


@patch_gov_uk_pay_availability_check()
class BankTransferWarningTestCase(BankTransferFlowTestCase):
    url = '/bank-transfer/warning/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    def test_redirected_if_accessed_after_choosing_debit_card(self):
        self.client.post(self.root_url, data={
            'payment_method': PaymentMethod.debit_card.name
        }, follow=True)
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    def test_warning_page_shows(self):
        response = self.choose_bank_transfer_payment_method()
        self.assertOnPage(response, 'bank_transfer_warning')


@patch_gov_uk_pay_availability_check()
class BankTransferPrisonerDetailsTestCase(BankTransferFlowTestCase):
    url = '/bank-transfer/details/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    def test_can_pass_warning_page(self):
        self.choose_bank_transfer_payment_method()

        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'prisoner_details_bank')

    def test_can_skip_back_to_payment_choice_page(self):
        self.choose_bank_transfer_payment_method()

        response = self.client.get(self.root_url, follow=True)
        self.assertOnPage(response, 'choose_method')
        self.assertContains(response, 'checked')

    @mock.patch('send_money.forms.BankTransferPrisonerDetailsForm.is_prisoner_known')
    def test_displays_errors_for_dropped_api_connection(self, mocked_is_prisoner_known):
        self.choose_bank_transfer_payment_method()

        mocked_is_prisoner_known.side_effect = ConnectionError
        with self.silence_logger():
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

    @mock.patch('send_money.forms.get_api_client')
    def test_search_not_limited_to_specific_prisons(self, mocked_api_client):
        self.choose_bank_transfer_payment_method()

        mocked_api_call = mocked_api_client().prisoner_validity().get
        mocked_api_call.return_value = {
            'count': 0,
            'results': []
        }
        self.client.post(self.url, data={
            'prisoner_number': 'A1231DE',
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }, follow=True)
        self.assertEqual(mocked_api_call.call_count, 1)
        mocked_api_call.assert_called_with(prisoner_number='A1231DE', prisoner_dob='1980-10-04')

    @override_settings(BANK_TRANSFER_PRISONS='DEF,ABC')
    @mock.patch('send_money.forms.get_api_client')
    def test_can_limit_search_to_specific_prisons(self, mocked_api_client):
        self.choose_bank_transfer_payment_method()

        mocked_api_call = mocked_api_client().prisoner_validity().get
        mocked_api_call.return_value = {
            'count': 0,
            'results': []
        }
        self.client.post(self.url, data={
            'prisoner_number': 'A1231DE',
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }, follow=True)
        self.assertEqual(mocked_api_call.call_count, 1)
        mocked_api_call.assert_called_with(prisoner_number='A1231DE', prisoner_dob='1980-10-04',
                                           prisons='ABC,DEF')


@patch_gov_uk_pay_availability_check()
class BankTransferReferenceTestCase(BankTransferFlowTestCase):
    url = '/bank-transfer/reference/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    def test_can_reach_reference_page(self):
        self.choose_bank_transfer_payment_method()

        response = self.fill_in_prisoner_details()
        self.assertOnPage(response, 'bank_transfer')

    def test_bank_transfer_page_clears_session(self):
        self.choose_bank_transfer_payment_method()
        for key in ['payment_method']:
            self.assertIn(key, self.client.session)

        self.fill_in_prisoner_details()
        for key in self.complete_session_keys:
            self.assertNotIn(key, self.client.session)
        response = self.client.get(self.url, follow=True)
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
        bank_transfer_reference = 'A1231DE/04/10/1980'
        self.assertContains(response, bank_transfer_reference)
        self.assertEqual(response.context['bank_transfer_reference'], bank_transfer_reference)


# DEBIT CARD FLOW


@override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                   SHOW_DEBIT_CARD_OPTION=True,
                   BANK_TRANSFER_PRISONS='',
                   DEBIT_CARD_PRISONS='')
class DebitCardFlowTestCase(BaseTestCase):
    complete_session_keys = [
        'payment_method',
        'prisoner_name',
        'prisoner_number',
        'prisoner_dob',
        'amount',
    ]

    @classmethod
    def patch_prisoner_details_check(cls):
        return mock.patch('send_money.forms.DebitCardPrisonerDetailsForm.is_prisoner_known',
                          return_value=True)

    def choose_debit_card_payment_method(self):
        response = self.client.post(self.root_url, data={
            'payment_method': PaymentMethod.debit_card.name
        }, follow=True)
        self.assertOnPage(response, 'prisoner_details_debit')

    def fill_in_prisoner_details(self, **kwargs):
        data = {
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1231DE',
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }
        data.update(kwargs)
        with self.patch_prisoner_details_check():
            return self.client.post(DebitCardPrisonerDetailsTestCase.url, data=data, follow=True)

    def fill_in_amount(self, **kwargs):
        data = {
            'amount': '17'
        }
        data.update(kwargs)
        with self.patch_prisoner_details_check():
            return self.client.post(DebitCardAmountTestCase.url, data=data, follow=True)


@patch_gov_uk_pay_availability_check()
class DebitCardPrisonerDetailsTestCase(DebitCardFlowTestCase):
    url = '/debit-card/details/'

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
        with self.silence_logger():
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

    @mock.patch('send_money.forms.get_api_client')
    def test_search_not_limited_to_specific_prisons(self, mocked_api_client):
        self.choose_debit_card_payment_method()

        mocked_api_call = mocked_api_client().prisoner_validity().get
        mocked_api_call.return_value = {
            'count': 0,
            'results': []
        }
        self.client.post(self.url, data={
            'prisoner_name': 'john smith',
            'prisoner_number': 'A1231DE',
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }, follow=True)
        self.assertEqual(mocked_api_call.call_count, 1)
        mocked_api_call.assert_called_with(prisoner_number='A1231DE', prisoner_dob='1980-10-04')

    @override_settings(DEBIT_CARD_PRISONS='DEF,ABC,ZZZ')
    @mock.patch('send_money.forms.get_api_client')
    def test_can_limit_search_to_specific_prisons(self, mocked_api_client):
        self.choose_debit_card_payment_method()

        mocked_api_call = mocked_api_client().prisoner_validity().get
        mocked_api_call.return_value = {
            'count': 0,
            'results': []
        }
        self.client.post(self.url, data={
            'prisoner_name': 'john smith',
            'prisoner_number': 'A1231DE',
            'prisoner_dob_0': '4',
            'prisoner_dob_1': '10',
            'prisoner_dob_2': '1980',
        }, follow=True)
        self.assertEqual(mocked_api_call.call_count, 1)
        mocked_api_call.assert_called_with(prisoner_number='A1231DE', prisoner_dob='1980-10-04',
                                           prisons='ABC,DEF,ZZZ')


@patch_gov_uk_pay_availability_check()
class DebitCardAmountTestCase(DebitCardFlowTestCase):
    url = '/debit-card/amount/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    @override_settings(SERVICE_CHARGED=False)
    def test_send_money_page_shows_no_service_charge(self):
        self.choose_debit_card_payment_method()
        response = self.fill_in_prisoner_details()

        self.assertNotContains(response, 'mtp-charges-charges')  # an element class

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('2.5'),
                       SERVICE_CHARGE_FIXED=Decimal('0.21'))
    def test_send_money_page_shows_service_charge(self):
        self.choose_debit_card_payment_method()
        response = self.fill_in_prisoner_details()

        self.assertContains(response, '2.5%')
        self.assertContains(response, '21p')

    @override_settings(SERVICE_CHARGED=False)
    def test_empty_form_shows_errors(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()

        with self.patch_prisoner_details_check():
            response = self.client.post(self.url, data={'amount': ''}, follow=True)
        self.assertOnPage(response, 'send_money_debit')
        form = response.context['form']
        self.assertTrue(form.errors)

    @override_settings(SERVICE_CHARGED=False)
    def test_amount_saved_and_can_be_changed(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()

        with self.patch_prisoner_details_check():
            response = self.client.post(self.url, data={'amount': '50'}, follow=True)
            self.assertOnPage(response, 'check_details')
            self.assertEqual(self.client.session.get('amount'), '50.00')
            response = self.client.get(self.url)
            self.assertContains(response, '"50.00"')
            response = self.client.post(self.url, data={'amount': '55.50'}, follow=True)
            self.assertOnPage(response, 'check_details')
            self.assertEqual(self.client.session.get('amount'), '55.50')


@patch_gov_uk_pay_availability_check()
class DebitCardCheckTestCase(DebitCardFlowTestCase):
    url = '/debit-card/check/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('2'),
                       SERVICE_CHARGE_FIXED=Decimal('1.21'))
    def test_check_page_displays_all_details(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        response = self.fill_in_amount()

        content = response.content.decode('utf8')
        self.assertIn('John Smith', content)
        self.assertIn('A1231DE', content)
        self.assertIn('4', content)
        self.assertIn('10', content)
        self.assertIn('1980', content)
        self.assertIn('£17', content)
        self.assertIn('£18.55', content)


@patch_gov_uk_pay_availability_check()
@override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                   SHOW_DEBIT_CARD_OPTION=True,
                   SERVICE_CHARGE_PERCENTAGE=Decimal('2.4'),
                   SERVICE_CHARGE_FIXED=Decimal('0.20'),
                   GOVUK_PAY_URL='https://pay.gov.local/v1')
class DebitCardPaymentTestCase(DebitCardFlowTestCase):
    url = '/debit-card/payment/'
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
                status=201
            )
            rsps.add(
                rsps.PATCH,
                api_url('/payments/%s/' % ref),
                status=200,
            )
            with self.patch_prisoner_details_check():
                response = self.client.get(self.url, follow=False)

            # check amount and service charge submitted to api
            self.assertEqual(json.loads(rsps.calls[1].request.body)['amount'], 1700)
            self.assertEqual(json.loads(rsps.calls[1].request.body)['service_charge'], 61)
            # check total charge submitted to govuk
            self.assertEqual(json.loads(rsps.calls[2].request.body)['amount'], 1761)

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
            with self.patch_prisoner_details_check(), self.silence_logger():
                response = self.client.get(self.url, follow=False)
            self.assertContains(response, 'We’re sorry, your payment could not be processed on this occasion')

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
            with self.patch_prisoner_details_check(), self.silence_logger():
                response = self.client.get(self.url, follow=False)
            self.assertContains(response, 'We’re sorry, your payment could not be processed on this occasion')


@patch_gov_uk_pay_availability_check()
@override_settings(SHOW_BANK_TRANSFER_OPTION=True,
                   SHOW_DEBIT_CARD_OPTION=True,
                   SERVICE_CHARGE_PERCENTAGE=Decimal('2.4'),
                   SERVICE_CHARGE_FIXED=Decimal('0.20'),
                   GOVUK_PAY_URL='https://pay.gov.local/v1')
class DebitCardConfirmationTestCase(DebitCardFlowTestCase):
    url = '/debit-card/confirmation/'

    def test_cannot_access_directly(self):
        response = self.client.get(self.url, follow=True)
        self.assertOnPage(response, 'choose_method')

    def test_confirmation_redirects_if_no_reference_param(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with self.patch_prisoner_details_check():
            response = self.client.get(self.url, data={'payment_ref': ''}, follow=True)
        self.assertOnPage(response, 'choose_method')

    @override_settings(ENVIRONMENT='prod')  # because non-prod environments don't send to @outside.local
    def test_confirmation(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            ref = 'wargle-blargle'
            processor_id = '3'
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/payments/%s/' % ref),
                json={
                    'processor_id': processor_id,
                    'recipient_name': 'John',
                    'amount': 1700,
                    'status': 'pending',
                    'created': datetime.datetime.now().isoformat() + 'Z',
                },
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % processor_id),
                json={
                    'state': {'status': 'success'},
                    'email': 'sender@outside.local',
                },
                status=200
            )
            rsps.add(
                rsps.PATCH,
                api_url('/payments/%s/' % ref),
                status=200,
            )
            with self.patch_prisoner_details_check():
                response = self.client.get(
                    self.url, {'payment_ref': ref}, follow=False
                )
            self.assertContains(response, 'success')

            # check session is cleared
            for key in self.complete_session_keys:
                self.assertNotIn(key, self.client.session)

            self.assertEqual('Send money to a prisoner: your payment was successful', mail.outbox[0].subject)
            self.assertTrue('WARGLE-B' in mail.outbox[0].body)
            self.assertTrue('£17' in mail.outbox[0].body)

            with self.patch_prisoner_details_check():
                response = self.client.get(
                    self.url, {'payment_ref': ref}, follow=True
                )
            self.assertOnPage(response, 'choose_method')

    def test_confirmation_handles_api_errors(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            ref = 'wargle-blargle'
            processor_id = '3'
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/payments/%s/' % ref),
                json={
                    'processor_id': processor_id,
                    'recipient_name': 'John',
                    'amount': 1700,
                    'status': 'pending',
                    'created': datetime.datetime.now().isoformat() + 'Z',
                },
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % processor_id),
                json={
                    'state': {'status': 'success'}, 'email': 'sender@outside.local'
                },
                status=200
            )
            rsps.add(
                rsps.PATCH,
                api_url('/payments/%s/' % ref),
                status=500,
            )
            with self.patch_prisoner_details_check(), self.silence_logger():
                response = self.client.get(
                    self.url, {'payment_ref': ref}, follow=False
                )
            self.assertContains(response, 'your payment could not be processed')
            self.assertContains(response, ref[:8].upper())

            # check session is cleared
            for key in self.complete_session_keys:
                self.assertNotIn(key, self.client.session)

    def test_confirmation_handles_govuk_errors(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            ref = 'wargle-blargle'
            processor_id = '3'
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/payments/%s/' % ref),
                json={
                    'processor_id': processor_id,
                    'recipient_name': 'John',
                    'amount': 1700,
                    'status': 'pending',
                    'created': datetime.datetime.now().isoformat() + 'Z',
                },
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % processor_id),
                status=500
            )
            with self.patch_prisoner_details_check(), self.silence_logger():
                response = self.client.get(
                    self.url, {'payment_ref': ref}, follow=False
                )
            self.assertContains(response, 'your payment could not be processed')
            self.assertContains(response, ref[:8].upper())

            # check session is cleared
            for key in self.complete_session_keys:
                self.assertNotIn(key, self.client.session)

    def test_confirmation_handles_rejected_card(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            ref = 'wargle-blargle'
            processor_id = '3'
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/payments/%s/' % ref),
                json={
                    'processor_id': processor_id,
                    'recipient_name': 'John',
                    'amount': 1700,
                    'status': 'pending',
                    'created': datetime.datetime.now().isoformat() + 'Z',
                },
                status=200,
            )
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % processor_id),
                json={
                    'state': {'status': 'failed'},
                    'email': 'sender@outside.local',
                },
                status=200
            )
            rsps.add(
                rsps.PATCH,
                api_url('/payments/%s/' % ref),
                status=200,
            )
            with self.patch_prisoner_details_check(), self.silence_logger():
                response = self.client.get(
                    self.url, {'payment_ref': ref}, follow=True
                )
            self.assertOnPage(response, 'check_details')

            # check session is kept
            for key in self.complete_session_keys:
                self.assertIn(key, self.client.session)

    def test_confirmation_redirects_for_completed_payments(self):
        self.choose_debit_card_payment_method()
        self.fill_in_prisoner_details()
        self.fill_in_amount()

        with responses.RequestsMock() as rsps:
            ref = 'wargle-blargle'
            processor_id = '3'
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/payments/%s/' % ref),
                json={
                    'processor_id': processor_id,
                    'recipient_name': 'John',
                    'amount': 1700,
                    'status': 'taken',
                    'created': datetime.datetime.now().isoformat() + 'Z',
                },
                status=200,
            )
            with self.patch_prisoner_details_check(), self.silence_logger():
                response = self.client.get(
                    self.url, {'payment_ref': ref}, follow=False
                )
            self.assertRedirects(response, '/')
