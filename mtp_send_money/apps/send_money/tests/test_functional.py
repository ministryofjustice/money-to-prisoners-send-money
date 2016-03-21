import datetime
import os
import unittest
from unittest import mock

from django.conf import settings
from django.test import override_settings
from mtp_utils.test_utils.functional_tests import FunctionalTestCase
import responses

from send_money.forms import PaymentMethod
from send_money.tests import split_prisoner_dob_for_post
from send_money.utils import govuk_url


class SendMoneyFunctionalTestCase(FunctionalTestCase):
    """
    Base class for all send-money functional tests
    """
    accessibility_scope_selector = '#content'

    def fill_in_send_money_form(self, data, payment_method):
        for key in data:
            field = self.driver.find_element_by_id('id_%s' % key)
            field.send_keys(data[key])
        # TODO: remove condition once TD allows showing bank transfers
        if not settings.HIDE_BANK_TRANSFER_OPTION:
            field = self.driver.find_element_by_xpath('//div[@id="id_payment_method"]//input[@value="%s"]'
                                                      % payment_method)
            field.click()


class SendMoneyFlows(SendMoneyFunctionalTestCase):
    # TODO: remove skip once TD allows showing bank transfers
    @unittest.skipIf(settings.HIDE_BANK_TRANSFER_OPTION, 'bank transfer is disabled')
    def test_bank_transfer_flow(self):
        self.driver.get(self.live_server_url)
        self.fill_in_send_money_form(split_prisoner_dob_for_post({
            'prisoner_name': 'James Halls',
            'prisoner_number': 'A1409AE',
            'prisoner_dob': '21/01/1989',
            'amount': '34.50',
        }), PaymentMethod.bank_transfer)
        self.driver.find_element_by_id('id_next_btn').click()
        self.driver.find_element_by_id('id_next_btn').click()
        self.assertInSource('<!-- bank_transfer -->')

    @unittest.skip('gov.uk pay functional testing not implemented')
    def test_debit_card_flow(self):
        self.driver.get(self.live_server_url)
        self.fill_in_send_money_form(split_prisoner_dob_for_post({
            'prisoner_name': 'James Halls',
            'prisoner_number': 'A1409AE',
            'prisoner_dob': '21/01/1989',
            'amount': '0.51',
        }), PaymentMethod.debit_card)
        self.driver.find_element_by_id('id_next_btn').click()
        # TODO: add gov.uk mock and test various responses


class SendMoneyDetailsPage(SendMoneyFunctionalTestCase):
    def check_service_charge(self, amount, expected):
        amount_field = self.driver.find_element_by_id('id_amount')
        total_field = self.driver.find_element_by_css_selector('.mtp-charges-total span')
        amount_field.clear()
        amount_field.send_keys(amount)
        self.assertEqual(total_field.text, expected)

    def test_page_contents(self):
        self.driver.get(self.live_server_url)
        self.assertEqual(self.driver.title, 'Send money to a prisoner - GOV.UK')
        self.assertEqual(self.driver.find_element_by_css_selector('h1').text, 'Who are you sending money to?')

    def test_service_charge_js(self):
        self.driver.get(self.live_server_url)
        self.check_service_charge('0', '£0.20')
        self.check_service_charge('10', '£10.44')
        self.check_service_charge('120.40', '£123.49')
        self.check_service_charge('0.01', '£0.21')
        self.check_service_charge('-12', '')
        self.check_service_charge('1', '£1.23')
        self.check_service_charge('17', '£17.61')
        self.check_service_charge('3.14     ', '£3.42')
        self.check_service_charge('a', '')
        self.check_service_charge('3', '£3.28')
        self.check_service_charge('-12', '')
        self.check_service_charge('.12', '')
        self.check_service_charge('32345', '£33,121.48')
        self.check_service_charge('10000000', '£10,240,000.20')
        self.check_service_charge('0.01', '£0.21')
        self.check_service_charge('9999999999999999999999', '£10,239,999,999.18')
        self.check_service_charge('three', '')
        self.check_service_charge('  3.1415     ', '')
        self.check_service_charge('0', '£0.20')
        self.check_service_charge('0.01', '£0.21')
        self.check_service_charge('0.1', '')
        self.check_service_charge('0.10', '£0.31')
        self.check_service_charge('0.87', '£1.09')
        self.check_service_charge('0.001', '')
        self.check_service_charge('0.005', '')


class SendMoneyCheckDetailsPage(SendMoneyFunctionalTestCase):
    def setUp(self):
        super().setUp()
        self.driver.get(self.live_server_url)
        self.fill_in_send_money_form(split_prisoner_dob_for_post({
            'prisoner_name': 'James Halls',
            'prisoner_number': 'A1409AE',
            'prisoner_dob': '21/01/1989',
            'amount': '34.50',
        }), PaymentMethod.bank_transfer)
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
            '0px',
            self.driver.find_element_by_css_selector('legend').value_of_css_property('margin-bottom')
        )
        self.assertEqual(
            'right',
            self.driver.find_element_by_xpath('//a[text()="Change this"]').value_of_css_property('text-align')
        )


class SendMoneyFeedbackPages(SendMoneyFunctionalTestCase):
    def test_feedback_page(self):
        self.driver.get(self.live_server_url + '/feedback/')
        self.assertInSource('Enter your feedback or any questions you have about this service.')

    def test_feedback_received_page(self):
        self.driver.get(self.live_server_url + '/feedback/success/')
        self.assertInSource('<h1>Thank you for your feedback</h1>')


@unittest.skipIf('DJANGO_TEST_REMOTE_INTEGRATION_URL' in os.environ, 'test only runs locally')
@override_settings(GOVUK_PAY_URL='http://payment.gov.uk',
                   GOVUK_PAY_AUTH_TOKEN='15a21a56-817a-43d4-bf8d-f01f298298e8')
class SendMoneyConfirmationPage(SendMoneyFunctionalTestCase):
    @mock.patch('send_money.views.get_api_client')
    def test_success_page(self, mocked_client):
        processor_id = '3'
        mocked_client().payments().get.return_value = {
            'processor_id': processor_id,
            'recipient_name': 'James Bond',
            'amount': 2000,
            'created': datetime.datetime.now().isoformat() + 'Z',
        }
        with responses.RequestsMock() as rsps:
            rsps.add(rsps.GET, govuk_url('/payments/%s' % processor_id), json={
                'status': 'SUCCEEDED'
            })

            self.driver.get(self.live_server_url + '/confirmation/?payment_ref=REF12345')
            self.assertInSource('<h1>Send money to a prisoner</h1>')
            self.assertInSource('Payment was successful')
            self.assertInSource('Your reference number is <strong>REF12345</strong>')
            self.assertInSource('What happens next?')
            self.assertInSource('James Bond')
            self.assertInSource('20')
            self.assertInSource('Print this page')

    @mock.patch('send_money.views.get_api_client')
    def test_failure_page(self, mocked_client):
        processor_id = '3'
        mocked_client().payments().get.return_value = {
            'processor_id': processor_id,
            'recipient_name': 'James Bond',
            'amount': 2000,
            'created': datetime.datetime.now().isoformat() + 'Z',
        }
        with responses.RequestsMock() as rsps:
            rsps.add(rsps.GET, govuk_url('/payments/%s' % processor_id), json={
                'status': 'FAILED'
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
            self.driver.get(self.live_server_url)
            link_element = self.driver.find_element_by_link_text(_footer_link['link_text'])
            link_element.click()
            self.assertInSource(_footer_link['page_content'])

        return test


SendMoneySupportPages.make_test_methods()
