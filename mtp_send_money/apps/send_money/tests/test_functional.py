import glob
import logging
import os
import socket
from urllib.parse import urlparse
import unittest

from django.conf import settings
from django.test import LiveServerTestCase
from selenium import webdriver

from send_money.forms import PaymentMethod
from send_money.tests import split_prisoner_dob_for_post

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
            self.driver = webdriver.Firefox()
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

    @unittest.skip('gov.uk pay testing not implemented')
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

    def check_service_charge(self, input, expected):
        amount_field = self.driver.find_element_by_id('id_amount')
        total_field = self.driver.find_element_by_css_selector('.mtp-charges-total span')
        amount_field.clear()
        amount_field.send_keys(input)
        self.assertEqual(total_field.text, expected)

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
