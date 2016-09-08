import datetime
import os
import random
import unittest
from unittest import mock

from django.conf import settings
from django.test import override_settings
from django.utils.timezone import now
from mtp_common.test_utils.functional_tests import FunctionalTestCase
import responses

from send_money.models import PaymentMethod
from send_money.tests import reload_payment_urls, split_prisoner_dob_for_post
from send_money.utils import govuk_url


class SendMoneyFunctionalTestCase(FunctionalTestCase):
    """
    Base class for all send-money functional tests
    """
    accessibility_scope_selector = '#content'

    def fill_in_prisoner_details_form(self, data, payment_method):
        if settings.SHOW_BANK_TRANSFER_OPTION and settings.SHOW_DEBIT_CARD_OPTION:
            field = self.driver.find_element_by_xpath('//a[@id="id_%s"]' % payment_method)
            field.click()
        for key in data:
            field = self.driver.find_element_by_id('id_%s' % key)
            field.send_keys(data[key])

    def fill_in_send_money_form(self, data):
        for key in data:
            field = self.driver.find_element_by_id('id_%s' % key)
            field.send_keys(data[key])


@unittest.skipIf('DJANGO_TEST_REMOTE_INTEGRATION_URL' in os.environ, 'test only runs locally')
class SendMoneyFlows(SendMoneyFunctionalTestCase):

    def test_bank_transfer_only_flow(self):
        with reload_payment_urls(self, show_debit_card=False, show_bank_transfer=True):
            self.driver.get(self.live_server_url)
            self.fill_in_prisoner_details_form(split_prisoner_dob_for_post({
                'prisoner_number': 'A1409AE',
                'prisoner_dob': '21/01/1989',
            }), PaymentMethod.bank_transfer)
            self.driver.find_element_by_id('id_next_btn').click()
            self.assertInSource('<!-- bank_transfer -->')

    def test_bank_transfer_flow(self):
        with reload_payment_urls(self, show_debit_card=True, show_bank_transfer=True):
            self.driver.get(self.live_server_url)
            self.fill_in_prisoner_details_form(split_prisoner_dob_for_post({
                'prisoner_number': 'A1409AE',
                'prisoner_dob': '21/01/1989',
            }), PaymentMethod.bank_transfer)
            self.driver.find_element_by_id('id_next_btn').click()
            self.assertInSource('<!-- bank_transfer -->')

    @unittest.skip('gov.uk pay functional testing not implemented')
    def test_debit_card_flow(self):
        with reload_payment_urls(self, show_debit_card=True, show_bank_transfer=True):
            self.driver.get(self.live_server_url)
            self.fill_in_prisoner_details_form(split_prisoner_dob_for_post({
                'prisoner_name': 'James Halls',
                'prisoner_number': 'A1409AE',
                'prisoner_dob': '21/01/1989',
            }), PaymentMethod.debit_card)
            self.driver.find_element_by_id('id_next_btn').click()
            self.fill_in_send_money_form({
                'amount': '0.51',
            })
            self.driver.find_element_by_id('id_next_btn').click()
            # TODO: add gov.uk mock and test various responses


@unittest.skipIf('DJANGO_TEST_REMOTE_INTEGRATION_URL' in os.environ, 'test only runs locally')
class SendMoneyDetailsPage(SendMoneyFunctionalTestCase):
    def test_page_contents(self):
        with reload_payment_urls(self, show_debit_card=True):
            self.driver.get(self.live_server_url)
            self.assertEqual(self.driver.title, 'Send money to a prisoner - GOV.UK')
            self.assertEqual(self.driver.find_element_by_css_selector('h1').text, 'Who are you sending money to?')

    def check_2_digit_entry(self):
        entry_year = random.randrange(0, 99)
        current_year = now().year
        century = 100 * (current_year // 100)
        era_boundary = int(str(current_year - 10)[-2:])
        if entry_year > era_boundary:
            expected_year = entry_year + century - 100
        else:
            expected_year = entry_year + century

        self.driver.get(self.live_server_url)
        year_field = self.driver.find_element_by_id('id_prisoner_dob_2')
        year_field.send_keys(str(entry_year))
        script = 'document.getElementById("id_prisoner_dob_2").focus();' \
                 'document.getElementById("id_prisoner_dob_1").focus();' \
                 'return document.getElementById("id_prisoner_dob_2").value;'
        self.assertEqual(self.driver.execute_script(script), str(expected_year),
                         msg='2-digit year %s did not format to expected %s' % (entry_year, expected_year))

    def test_2_digit_year_entry_using_javascript_in_bank_transfer_flow(self):
        with reload_payment_urls(self, show_bank_transfer=True, show_debit_card=False):
            self.check_2_digit_entry()

    def test_2_digit_year_entry_using_javascript_in_debit_card_flow(self):
        with reload_payment_urls(self, show_bank_transfer=False, show_debit_card=True):
            self.check_2_digit_entry()

    def test_service_charge_js(self):
        def check_service_charge(amount, expected):
            amount_field = self.driver.find_element_by_id('id_amount')
            total_field = self.driver.find_element_by_css_selector('.mtp-charges-total span')
            amount_field.clear()
            amount_field.send_keys(amount)
            self.assertEqual(total_field.text, expected)

        with reload_payment_urls(self, show_debit_card=True):
            self.driver.get(self.live_server_url)
            self.fill_in_prisoner_details_form(split_prisoner_dob_for_post({
                'prisoner_name': 'James Halls',
                'prisoner_number': 'A1409AE',
                'prisoner_dob': '21/01/1989',
            }), PaymentMethod.debit_card)
            self.driver.find_element_by_id('id_next_btn').click()
            check_service_charge('0', '£0.20')
            check_service_charge('10', '£10.44')
            check_service_charge('120.40', '£123.49')
            check_service_charge('0.01', '£0.21')
            check_service_charge('-12', '')
            check_service_charge('1', '£1.23')
            check_service_charge('17', '£17.61')
            check_service_charge('3.14     ', '£3.42')
            check_service_charge('a', '')
            check_service_charge('3', '£3.28')
            check_service_charge('-12', '')
            check_service_charge('.12', '')
            check_service_charge('32345', '£33,121.48')
            check_service_charge('10000000', '£10,240,000.20')
            check_service_charge('0.01', '£0.21')
            check_service_charge('9999999999999999999999', '£10,239,999,999.18')
            check_service_charge('three', '')
            check_service_charge('  3.1415     ', '')
            check_service_charge('0', '£0.20')
            check_service_charge('0.01', '£0.21')
            check_service_charge('0.1', '')
            check_service_charge('0.10', '£0.31')
            check_service_charge('0.87', '£1.09')
            check_service_charge('0.001', '')
            check_service_charge('0.005', '')


@unittest.skipIf('DJANGO_TEST_REMOTE_INTEGRATION_URL' in os.environ, 'test only runs locally')
class SendMoneyCheckDetailsPage(SendMoneyFunctionalTestCase):
    def setUp(self):
        with reload_payment_urls(self, show_debit_card=True):
            super().setUp()
            self.driver.get(self.live_server_url)
            self.fill_in_prisoner_details_form(split_prisoner_dob_for_post({
                'prisoner_name': 'James Halls',
                'prisoner_number': 'A1409AE',
                'prisoner_dob': '21/01/1989',
            }), PaymentMethod.debit_card)
            self.driver.find_element_by_id('id_next_btn').click()
            self.fill_in_send_money_form({
                'amount': '34.50',
            })
            self.driver.find_element_by_id('id_next_btn').click()
            self.assertCurrentUrl('/check-details/')
            self.assertEqual(self.driver.title, 'Check details - Send money to a prisoner - GOV.UK')

    def test_content(self):
        self.assertInSource('Name: James Halls')
        self.assertInSource('Date of birth: 21/01/1989')
        self.assertInSource('Prisoner number: A1409AE')
        self.assertInSource('Total to prisoner: £34.50')
        self.assertInSource('value="Make payment"')

    def test_style(self):
        self.assertEqual('48px', self.driver.find_element_by_css_selector('h1').value_of_css_property('font-size'))
        self.assertEqual(
            '4px',
            self.driver.find_element_by_css_selector('h2').value_of_css_property('margin-bottom')
        )


class SendMoneyFeedbackPages(SendMoneyFunctionalTestCase):
    def test_feedback_page(self):
        self.driver.get(self.live_server_url + '/feedback/')
        self.assertInSource('Enter your feedback or any questions you have about this service.')

    def test_feedback_received_page(self):
        self.driver.get(self.live_server_url + '/feedback/success/')
        self.assertInSource('<h1 class="heading-xlarge">Thank you for your feedback</h1>')


@unittest.skipIf('DJANGO_TEST_REMOTE_INTEGRATION_URL' in os.environ, 'test only runs locally')
@override_settings(GOVUK_PAY_URL='http://payment.gov.uk',
                   GOVUK_PAY_AUTH_TOKEN='15a21a56-817a-43d4-bf8d-f01f298298e8')
class SendMoneyConfirmationPage(SendMoneyFunctionalTestCase):
    @mock.patch('send_money.views.get_api_client')
    def test_success_page(self, mocked_client):
        with reload_payment_urls(self, show_debit_card=True):
            processor_id = '3'
            mocked_client().payments().get.return_value = {
                'processor_id': processor_id,
                'recipient_name': 'James Bond',
                'amount': 2000,
                'created': datetime.datetime.now().isoformat() + 'Z',
            }
            with responses.RequestsMock() as rsps:
                rsps.add(rsps.GET, govuk_url('/payments/%s' % processor_id), json={
                    'state': {'status': 'success'}, 'email': 'sender@outside.local'
                })

                self.driver.get(self.live_server_url + '/confirmation/?payment_ref=REF12345')
                self.assertInSource('<h1 class="heading-xlarge">Send money to a prisoner</h1>')
                self.assertInSource('Payment was successful')
                self.assertInSource('Your reference number is <strong>REF12345</strong>')
                self.assertInSource('What happens next?')
                self.assertInSource('James Bond')
                self.assertInSource('20')
                self.assertInSource('Print this page')

    @unittest.skip('error pages handled by gov.uk')
    @mock.patch('send_money.views.get_api_client')
    def test_failure_page(self, mocked_client):
        with reload_payment_urls(self, show_debit_card=True):
            processor_id = '3'
            mocked_client().payments().get.return_value = {
                'processor_id': processor_id,
                'recipient_name': 'James Bond',
                'amount': 2000,
                'created': datetime.datetime.now().isoformat() + 'Z',
            }
            with responses.RequestsMock() as rsps:
                rsps.add(rsps.GET, govuk_url('/payments/%s' % processor_id), json={
                    'state': {'status': 'failed'}
                })

                self.driver.get(self.live_server_url + '/confirmation/?payment_ref=REF12345')
                self.assertInSource('We’re sorry, your payment could not be processed on this occasion')
                self.assertInSource('Your reference number is <strong>REF12345</strong>')


class SendMoneySupportPages(SendMoneyFunctionalTestCase):
    footer_links = [
        {
            'link_name': 'terms',
            'link_text': 'Terms and conditions',
            'page_content': 'Terms and conditions',
        },
        {
            'link_name': 'cookies',
            'link_text': 'Cookies',
            'page_content': 'How cookies are used on GOV.UK',
        },
    ]

    @classmethod
    def make_test_methods(cls):
        for footer_link in cls.footer_links:
            setattr(cls, 'test_footer_link__%s' % footer_link['link_name'],
                    cls.make_test_method(footer_link))

    @classmethod
    def make_test_method(cls, _footer_link):
        def test(self):
            with reload_payment_urls(self, show_debit_card=True):
                self.driver.get(self.live_server_url)
                link_element = self.driver.find_element_by_link_text(_footer_link['link_text'])
                link_element.click()
                self.assertInSource(_footer_link['page_content'])

        return test


SendMoneySupportPages.make_test_methods()
