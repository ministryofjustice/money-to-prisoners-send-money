import datetime
import decimal
import os
import random
import unittest
from unittest import mock

from django.test import override_settings
from django.utils.timezone import now
from mtp_common.test_utils.functional_tests import FunctionalTestCase
import responses

from send_money.models import PaymentMethod
from send_money.tests import mock_auth
from send_money.utils import api_url, govuk_url


class SendMoneyFunctionalTestCase(FunctionalTestCase):
    """
    Base class for all send-money functional tests
    """
    accessibility_scope_selector = '#content'

    @classmethod
    def patch_view_chain_form_checking(cls):
        return mock.patch('send_money.views.SendMoneyFormView.is_form_enabled', return_value=False)

    def assertOnPage(self, url_name):  # noqa: N802
        self.assertInSource('<!-- %s -->' % url_name)

    def make_payment_method_choice(self, payment_method):
        self.driver.find_element_by_id('id_%s' % payment_method).click()
        self.click_on_text('Continue')

    def fill_in_form(self, data):
        for key, value in data.items():
            field = self.driver.find_element_by_id('id_%s' % key)
            field.send_keys(value)


@unittest.skipIf('DJANGO_TEST_REMOTE_INTEGRATION_URL' in os.environ, 'test only runs locally')
class SendMoneyFlows(SendMoneyFunctionalTestCase):
    def test_bank_transfer_flow(self):
        self.driver.get(self.live_server_url + '/en-gb/')
        self.make_payment_method_choice(PaymentMethod.bank_transfer)
        self.driver.find_element_by_id('id_next_btn').click()
        self.fill_in_form({
            'prisoner_number': 'A1409AE',
            'prisoner_dob_0': '21',
            'prisoner_dob_1': '1',
            'prisoner_dob_2': '1989',
        })
        self.driver.find_element_by_id('id_next_btn').click()
        self.assertOnPage('bank_transfer')

    @unittest.skip('gov.uk pay functional testing not implemented')
    def test_debit_card_flow(self):
        self.driver.get(self.live_server_url + '/en-gb/')
        self.make_payment_method_choice(PaymentMethod.debit_card)
        self.fill_in_form({
            'prisoner_name': 'James Halls',
            'prisoner_number': 'A1409AE',
            'prisoner_dob_0': '21',
            'prisoner_dob_1': '1',
            'prisoner_dob_2': '1989',
        })
        self.driver.find_element_by_id('id_next_btn').click()
        self.fill_in_form({
            'amount': '0.51',
        })
        self.driver.find_element_by_id('id_next_btn').click()
        # TODO: add gov.uk mock and test various responses


@unittest.skipIf('DJANGO_TEST_REMOTE_INTEGRATION_URL' in os.environ, 'test only runs locally')
class SendMoneyDetailsPage(SendMoneyFunctionalTestCase):
    def check_2_digit_entry(self):
        entry_year = random.randrange(0, 99)
        current_year = now().year
        century = 100 * (current_year // 100)
        era_boundary = int(str(current_year - 10)[-2:])
        if entry_year > era_boundary:
            expected_year = entry_year + century - 100
        else:
            expected_year = entry_year + century

        year_field = self.driver.find_element_by_id('id_prisoner_dob_2')
        year_field.send_keys(str(entry_year))
        script = 'document.getElementById("id_prisoner_dob_2").focus();' \
                 'document.getElementById("id_prisoner_dob_1").focus();' \
                 'return document.getElementById("id_prisoner_dob_2").value;'
        self.assertEqual(self.driver.execute_script(script), str(expected_year),
                         msg='2-digit year %s did not format to expected %s' % (entry_year, expected_year))

    def test_2_digit_year_entry_using_javascript_in_bank_transfer_flow(self):
        self.driver.get(self.live_server_url + '/en-gb/')
        self.driver.find_element_by_id('id_bank_transfer').click()
        self.driver.find_element_by_id('id_next_btn').click()
        self.check_2_digit_entry()

    def test_2_digit_year_entry_using_javascript_in_debit_card_flow(self):
        self.driver.get(self.live_server_url + '/en-gb/')
        self.driver.find_element_by_id('id_debit_card').click()
        self.check_2_digit_entry()

    @override_settings(SERVICE_CHARGE_PERCENTAGE=decimal.Decimal('2.4'),
                       SERVICE_CHARGE_FIXED=decimal.Decimal('0.20'))
    def test_service_charge_js(self):
        def check_service_charge(amount, expected):
            amount_field = self.driver.find_element_by_id('id_amount')
            total_field = self.driver.find_element_by_css_selector('.mtp-charges-total span')
            amount_field.clear()
            amount_field.send_keys(amount)
            self.assertEqual(total_field.text, expected)

        self.driver.get(self.live_server_url + '/en-gb/')
        self.driver.find_element_by_id('id_debit_card').click()
        self.fill_in_form({
            'prisoner_name': 'James Halls',
            'prisoner_number': 'A1409AE',
            'prisoner_dob_0': '21',
            'prisoner_dob_1': '1',
            'prisoner_dob_2': '1989',
        })
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
    def test_content(self):
        self.driver.get(self.live_server_url + '/en-gb/')
        self.driver.find_element_by_id('id_debit_card').click()
        self.fill_in_form({
            'prisoner_name': 'James Halls',
            'prisoner_number': 'A1409AE',
            'prisoner_dob_0': '21',
            'prisoner_dob_1': '1',
            'prisoner_dob_2': '1989',
        })
        self.driver.find_element_by_id('id_next_btn').click()
        self.fill_in_form({
            'amount': '34.50',
        })
        self.driver.find_element_by_id('id_next_btn').click()
        self.assertCurrentUrl('/en-gb/debit-card/check/')
        self.assertIn('Check details', self.driver.title)
        self.assertInSource('James Halls')
        self.assertInSource('21/01/1989')
        self.assertInSource('A1409AE')
        self.assertInSource('£34.50')


class SendMoneyFeedbackPages(SendMoneyFunctionalTestCase):
    def test_feedback_page(self):
        self.driver.get(self.live_server_url + '/en-gb/contact-us/')
        self.assertInSource('Enter your questions or feedback')

    def test_feedback_received_page(self):
        self.driver.get(self.live_server_url + '/en-gb/contact-us/success/')
        self.assertInSource('Thank you')


@unittest.skipIf('DJANGO_TEST_REMOTE_INTEGRATION_URL' in os.environ, 'test only runs locally')
@override_settings(GOVUK_PAY_URL='https://pay.gov.local/v1',
                   GOVUK_PAY_AUTH_TOKEN='15a21a56-817a-43d4-bf8d-f01f298298e8')
class SendMoneyConfirmationPage(SendMoneyFunctionalTestCase):
    def test_success_page(self):
        ref = 'f469ec29-fb86-40db-a9e0-6faa409533be'
        processor_id = '3'
        with responses.RequestsMock() as rsps, self.patch_view_chain_form_checking():
            mock_auth(rsps)
            rsps.add(rsps.GET, api_url('/payments/%s/' % ref), json={
                'uuid': ref,
                'processor_id': processor_id,
                'recipient_name': 'James Bond',
                'amount': 2000,
                'status': 'pending',
                'created': datetime.datetime.now().isoformat() + 'Z',
                'prisoner_number': 'A5544CD',
                'prisoner_dob': '1992-12-05'
            })
            rsps.add(rsps.GET, govuk_url('/payments/%s' % processor_id), json={
                'reference': ref,
                'state': {'status': 'success', 'finished': True},
                'amount': 2000,
                'payment_id': processor_id,
                'email': 'sender@outside.local',
                '_links': {
                    'events': {'href': govuk_url('/payments/%s/events' % processor_id), 'method': 'GET'}
                }
            })
            rsps.add(rsps.PATCH, api_url('/payments/%s/' % ref), json={
                'uuid': ref,
                'processor_id': processor_id,
                'recipient_name': 'James Bond',
                'amount': 2000,
                'status': 'pending',
                'created': datetime.datetime.now().isoformat() + 'Z',
                'prisoner_number': 'A5544CD',
                'prisoner_dob': '1992-12-05',
                'email': 'sender@outside.local',
            })

            self.driver.get(self.live_server_url + '/en-gb/debit-card/confirmation/?payment_ref=' + ref)
        self.assertInSource('Payment successful')
        self.assertInSource('<strong>F469EC29</strong>')
        self.assertInSource('James Bond')
        self.assertInSource('£20')
        self.assertInSource('Print this page')

    @unittest.skip('error pages handled by gov.uk')
    def test_failure_page(self):
        processor_id = '3'
        with responses.RequestsMock() as rsps:
            rsps.add(rsps.GET, api_url('/payments/'), json={
                'uuid': 'wargle-blargle',
                'processor_id': processor_id,
                'recipient_name': 'James Bond',
                'amount': 2000,
                'status': 'pending',
                'created': datetime.datetime.now().isoformat() + 'Z',
                'prisoner_number': 'A5544CD',
                'prisoner_dob': '1992-12-05'
            })
            rsps.add(rsps.GET, govuk_url('/payments/%s' % processor_id), json={
                'state': {'status': 'failed'}
            })

            self.driver.get(self.live_server_url + '/en-gb/debit-card/confirmation/?payment_ref=REF12345')
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
            'link_name': 'privacy',
            'link_text': 'Privacy policy',
            'page_content': 'Privacy policy',
        },
        {
            'link_name': 'cookies',
            'link_text': 'Cookies',
            'page_content': 'Cookies we use to improve our service',
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
            self.driver.get(self.live_server_url + '/en-gb/')
            link_element = self.driver.find_element_by_link_text(_footer_link['link_text'])
            link_element.click()
            self.assertInSource(_footer_link['page_content'])

        return test


SendMoneySupportPages.make_test_methods()
