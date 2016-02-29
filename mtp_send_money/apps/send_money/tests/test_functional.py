import datetime
import glob
import logging
import os
import socket
import unittest
from unittest import mock
from urllib.parse import urlparse

from django.conf import settings
from django.test import LiveServerTestCase, override_settings
import responses
from selenium import webdriver

from send_money.forms import PaymentMethod
from send_money.tests import split_prisoner_dob_for_post
from send_money.utils import govuk_url

logger = logging.getLogger('mtp')


@unittest.skipUnless('RUN_FUNCTIONAL_TESTS' in os.environ, 'functional tests are disabled')
class SendMoneyFunctionalTestCase(LiveServerTestCase):
    @classmethod
    def _databases_names(cls, include_mirrors=True):
        # this app has no databases
        return []

    def setUp(self):
        web_driver = os.environ.get('WEBDRIVER', 'phantomjs')
        if web_driver == 'firefox':
            fp = webdriver.FirefoxProfile()
            fp.set_preference('browser.startup.homepage', 'about:blank')
            fp.set_preference('startup.homepage_welcome_url', 'about:blank')
            fp.set_preference('startup.homepage_welcome_url.additional', 'about:blank')
            self.driver = webdriver.Firefox(firefox_profile=fp)
        elif web_driver == 'chrome':
            paths = glob.glob('node_modules/selenium-standalone/.selenium/chromedriver/*-chromedriver')
            paths = filter(lambda path: os.path.isfile(path) and os.access(path, os.X_OK),
                           paths)
            try:
                self.driver = webdriver.Chrome(executable_path=next(paths))
            except StopIteration:
                self.fail('Cannot find Chrome driver')
        else:
            path = './node_modules/phantomjs/lib/phantom/bin/phantomjs'
            self.driver = webdriver.PhantomJS(executable_path=path)

        self.driver.set_window_size(1000, 1000)

    def tearDown(self):
        self.driver.quit()

    def load_test_data(self):
        logger.info('Reloading test data')
        try:
            with socket.socket() as sock:
                sock.connect((
                    urlparse(settings.API_URL).netloc.split(':')[0],
                    os.environ.get('CONTROLLER_PORT', 8800)
                ))
                sock.sendall(b'load_test_data')
                response = sock.recv(1024).strip()
                if response != b'done':
                    logger.error('Test data not reloaded!')
        except OSError:
            logger.exception('Error communicating with test server controller socket')

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
        self.assertIn('<!-- bank_transfer -->', self.driver.page_source)

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
        self.assertEqual(self.driver.current_url, self.live_server_url + '/check-details/')
        self.assertEqual(self.driver.title, 'Check details - Send money to a prisoner - GOV.UK')

    def test_content(self):
        self.assertIn('Name: James Halls', self.driver.page_source)
        self.assertIn('Date of birth: 21/01/1989', self.driver.page_source)
        self.assertIn('Prisoner number: A1409AE', self.driver.page_source)
        self.assertIn('Total to prisoner: £34.50', self.driver.page_source)
        self.assertIn('value="Make payment"', self.driver.page_source)

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
        self.assertIn('Enter your feedback or any questions you have about this service.',
                      self.driver.page_source)

    def test_feedback_received_page(self):
        self.driver.get(self.live_server_url + '/feedback/success/')
        self.assertIn('<h1>Thank you for your feedback</h1>', self.driver.page_source)


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
            self.assertIn('<h1>Send money to a prisoner</h1>', self.driver.page_source)
            self.assertIn('Payment was successful', self.driver.page_source)
            self.assertIn('Your reference number is <strong>REF12345</strong>', self.driver.page_source)
            self.assertIn('What happens next?', self.driver.page_source)
            self.assertIn('James Bond', self.driver.page_source)
            self.assertIn('20', self.driver.page_source)
            self.assertIn('Print this page', self.driver.page_source)

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
            self.assertIn('We’re sorry, your payment could not be processed on this occasion', self.driver.page_source)
            self.assertIn('Your reference number is <strong>REF12345</strong>', self.driver.page_source)


class SendMoneySupportPages(SendMoneyFunctionalTestCase):
    footer_links = [
        {
            'link_name': 'privacy_policy',
            'link_text': 'Privacy Policy',
            'page_content': 'Privacy Policy',
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
            self.assertIn(_footer_link['page_content'], self.driver.page_source)

        return test


SendMoneySupportPages.make_test_methods()
