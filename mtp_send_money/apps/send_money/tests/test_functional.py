import os
import unittest

from django.conf import settings
from django.test import LiveServerTestCase
from selenium import webdriver

from send_money.forms import PaymentMethod


@unittest.skipUnless('RUN_FUNCTIONAL_TESTS' in os.environ, 'functional tests are disabled')
class SendMoneyFunctionalTestCase(LiveServerTestCase):

    @classmethod
    def _databases_names(cls, include_mirrors=True):
        # this app has no databases
        return []

    def setUp(self):
        path = './node_modules/phantomjs/lib/phantom/bin/phantomjs'
        self.driver = webdriver.PhantomJS(executable_path=path)
        self.driver.set_window_size(1000, 1000)

    def tearDown(self):
        self.driver.quit()

    def fill_in_send_money_form(self, data, payment_method):
        for key in data:
            field = self.driver.find_element_by_id('id_%s' % key)
            field.send_keys(data[key])
        # TODO: remove condition once TD allows showing bank transfers
        if not settings.HIDE_BANK_TRANSFER_OPTION:
            field = self.driver.find_element_by_xpath('//ul[@id="id_payment_method"]//input[@value="%s"]'
                                                      % payment_method)
            field.click()

    # TODO: remove skip once TD allows showing bank transfers
    @unittest.skipIf(settings.HIDE_BANK_TRANSFER_OPTION, 'bank transfer is disabled')
    def test_bank_transfer_flow(self):
        self.driver.get(self.live_server_url)
        self.fill_in_send_money_form({
            'prisoner_name': 'James Halls',
            'prisoner_number': 'A1409AE',
            'prisoner_dob': '21/01/1989',
            'amount': '34.50',
        }, PaymentMethod.bank_transfer)
        self.driver.find_element_by_id('id_next_btn').click()
        self.driver.find_element_by_id('id_next_btn').click()
        self.assertIn('<!-- bank_transfer -->', self.driver.page_source)

    def test_debit_card_flow(self):
        self.driver.get(self.live_server_url)
        self.fill_in_send_money_form({
            'prisoner_name': 'James Halls',
            'prisoner_number': 'A1409AE',
            'prisoner_dob': '21/01/1989',
            'amount': '0.51',
        }, PaymentMethod.debit_card)
        self.driver.find_element_by_id('id_next_btn').click()
        self.driver.find_element_by_id('id_next_btn').click()
        self.assertIn('<!-- debit_card -->', self.driver.page_source)
