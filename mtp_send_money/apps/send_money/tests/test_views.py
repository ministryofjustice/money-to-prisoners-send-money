import datetime
from contextlib import contextmanager
from decimal import Decimal
import json
import logging
import unittest
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.urlresolvers import reverse, reverse_lazy
from django.test.testcases import SimpleTestCase
from django.test.utils import override_settings
from django.utils.html import escape
from requests import ConnectionError
import responses

from send_money.forms import SendMoneyForm
from send_money.tests import mock_auth, split_prisoner_dob_for_post
from send_money.utils import govuk_url, api_url
from . import reload_payment_urls

SAMPLE_FORM = {
    'prisoner_name': 'John Smith',
    'prisoner_number': 'A1231DE',
    'prisoner_dob': '1980-10-04',
    'amount': '10.00',
}


class BaseTestCase(SimpleTestCase):
    start_url = reverse_lazy('send_money:send_money_debit')

    @property
    def check_details_url(self):
        return reverse_lazy('send_money:check_details')

    @contextmanager
    def silence_logger(self, name='mtp'):
        logger = logging.getLogger(name)
        level = logger.level
        logger.setLevel(logging.CRITICAL)
        yield
        logger.setLevel(level)

    def assertOnPage(self, response, url_name):  # noqa
        self.assertContains(response, '<!-- %s -->' % url_name)

    def assertPageNotDirectlyAccessible(self):  # noqa
        response = self.client.get(self.url)
        if settings.SHOW_DEBIT_CARD_OPTION and settings.SHOW_BANK_TRANSFER_OPTION:
            opening_url = reverse_lazy('send_money:choose_method')
        elif settings.SHOW_DEBIT_CARD_OPTION:
            opening_url = reverse_lazy('send_money:send_money_debit')
        elif settings.SHOW_BANK_TRANSFER_OPTION:
            opening_url = reverse_lazy('send_money:send_money_bank')

        self.assertRedirects(response, opening_url)

    def populate_session(self, **kwargs):
        session = self.client.session
        for key, default in SAMPLE_FORM.items():
            session[key] = kwargs.get(key, SAMPLE_FORM[key])
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def _prepare_post_data(self, mocked_api_client, update_data=None, replace_data=None):
        prisoner_details = {
            'prisoner_number': SAMPLE_FORM['prisoner_number'],
            'prisoner_dob': SAMPLE_FORM['prisoner_dob'],
        }
        mocked_client = mocked_api_client.get_authenticated_connection()
        mocked_client.prisoner_validity().get.return_value = {
            'count': 1,
            'results': [prisoner_details]
        }
        if replace_data is None:
            data = {
                'prisoner_name': SAMPLE_FORM['prisoner_name'],
                'amount': SAMPLE_FORM['amount'],
            }
            data.update(prisoner_details)
        else:
            data = replace_data
        if update_data:
            data.update(update_data)
        return split_prisoner_dob_for_post(data)

    def submit_send_money_form(self, mocked_api_client, update_data=None, replace_data=None, follow=False):
        data = self._prepare_post_data(mocked_api_client, update_data=update_data, replace_data=replace_data)
        return self.client.post(self.start_url, data=data, follow=follow)

    def submit_check_details_form(self, mocked_api_client, update_data=None, replace_data=None, follow=False):
        data = self._prepare_post_data(mocked_api_client, update_data=update_data, replace_data=replace_data)
        return self.client.post(self.check_details_url, data=data, follow=follow)


@unittest.skipUnless(settings.SHOW_DEBIT_CARD_OPTION and settings.SHOW_BANK_TRANSFER_OPTION,
                     'Both debit cards and bank transfers must be enabled to test method choice page')
class ChooseMethodViewTestCase(BaseTestCase):
    url = reverse_lazy('send_money:choose_method')

    def test_both_choices_listed(self):
        response = self.client.get(self.url)
        self.assertContains(response, reverse('send_money:send_money_debit'))
        self.assertContains(response, reverse('send_money:send_money_bank'))

    def test_experiment_choice_cookie_and_ordering(self):
        from send_money.views import ChooseMethodView

        response = self.client.get(self.url)
        variation = response.cookies.get(ChooseMethodView.experiment_cookie_name)
        if variation:
            variation = variation.value
        self.assertTrue(variation, 'Cookie not saved')

        content = response.content.decode(response.charset)
        if variation == 'debit-card':
            self.assertLess(content.find(reverse('send_money:send_money_debit')),
                            content.find(reverse('send_money:send_money_bank')),
                            'Debit card option should appear first according to experiment')
        else:
            self.assertLess(content.find(reverse('send_money:send_money_bank')),
                            content.find(reverse('send_money:send_money_debit')),
                            'Bank transfer option should appear first according to experiment')


class SendMoneyDebitViewTestCase(BaseTestCase):
    url = reverse_lazy('send_money:send_money_debit')

    def test_send_money_page_loads(self):
        with reload_payment_urls(self, show_debit_card=True):
            response = self.client.get(self.url)
            self.assertOnPage(response, 'send_money_debit')

    def test_request_user_is_anonymous(self):
        response = self.client.get(self.url)
        request = response.context['request']
        self.assertTrue(request.user.is_anonymous())

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('2.5'),
                       SERVICE_CHARGE_FIXED=Decimal('0.21'))
    def test_send_money_page_shows_service_charge(self):
        with reload_payment_urls(self, show_debit_card=True):
            response = self.client.get(self.url)
            self.assertContains(response, '2.5%')
            self.assertContains(response, '21p')

    @override_settings(SERVICE_CHARGED=False)
    def test_send_money_page_shows_no_service_charge(self):
        with reload_payment_urls(self, show_debit_card=True):
            response = self.client.get(self.url)
            self.assertNotContains(response, 'service charge')

    @mock.patch('send_money.utils.api_client')
    def test_send_money_page_previews_form(self, mocked_api_client):
        with reload_payment_urls(self, show_debit_card=True):
            response = self.submit_send_money_form(mocked_api_client, follow=True)
            self.assertOnPage(response, 'check_details')

    @mock.patch('send_money.forms.PrisonerDetailsForm.check_prisoner_validity')
    def test_send_money_page_displays_errors_for_invalid_prisoner_number(self, mocked_check_prisoner_validity):
        with reload_payment_urls(self, show_debit_card=True):
            response = self.client.post(self.url, data=split_prisoner_dob_for_post({
                'prisoner_name': 'John Smith',
                'prisoner_number': 'a1231a1',
                'prisoner_dob': '1980-10-04',
                'amount': '10.00',
            }))
            self.assertContains(response, 'Incorrect prisoner number format')
            form = response.context['form']
            self.assertTrue(form.errors)
            self.assertEqual(mocked_check_prisoner_validity.call_count, 0)

    @mock.patch('send_money.forms.PrisonerDetailsForm.check_prisoner_validity')
    def test_send_money_page_displays_errors_for_invalid_prisoner_dob(self, mocked_check_prisoner_validity):
        with reload_payment_urls(self, show_debit_card=True):
            response = self.client.post(self.url, data={
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A1231DE',
                'amount': '10.00',
            })
            self.assertContains(response, 'This field is required')
            form = response.context['form']
            self.assertTrue(form.errors)
            self.assertEqual(mocked_check_prisoner_validity.call_count, 0)

    @mock.patch('send_money.forms.PrisonerDetailsForm.check_prisoner_validity')
    def test_send_money_page_displays_errors_for_invalid_prisoner_details(self, mocked_check_prisoner_validity):
        mocked_check_prisoner_validity.return_value = False
        with reload_payment_urls(self, show_debit_card=True):
            response = self.client.post(self.url, data=split_prisoner_dob_for_post({
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A1231DE',
                'prisoner_dob': '1980-10-04',
                'amount': '10.00',
            }))
            self.assertContains(response, escape('No prisoner matches the details you’ve supplied'))
            form = response.context['form']
            self.assertTrue(form.errors)

    @mock.patch('send_money.forms.PrisonerDetailsForm.check_prisoner_validity')
    def test_send_money_page_displays_errors_for_dropped_api_connection(self, mocked_check_prisoner_validity):
        mocked_check_prisoner_validity.side_effect = ConnectionError
        with reload_payment_urls(self, show_debit_card=True):
            response = self.client.post(self.url, data=split_prisoner_dob_for_post({
                'prisoner_name': 'John Smith',
                'prisoner_number': 'A1231DE',
                'prisoner_dob': '1980-10-04',
                'amount': '10.00',
            }))
            self.assertContains(response, 'This service is currently unavailable')
            form = response.context['form']
            self.assertTrue(form.errors)

    @mock.patch('send_money.utils.api_client')
    def test_send_money_page_allows_changing_form(self, mocked_api_client):
        with reload_payment_urls(self, show_debit_card=True):
            response = self.submit_send_money_form(mocked_api_client, follow=True)
            self.assertOnPage(response, 'check_details')
            response = self.client.get(self.start_url + '?change')
            self.assertOnPage(response, 'send_money_debit')
            self.assertContains(response, '"John Smith"')
            self.assertContains(response, '"A1231DE"')
            self.assertContains(response, '"4"')
            self.assertContains(response, '"10"')
            self.assertContains(response, '"1980"')
            self.assertContains(response, '"10.00"')

    @mock.patch('send_money.utils.api_client')
    def test_send_money_page_can_proceed_to_debit_card(self, mocked_api_client):
        with reload_payment_urls(self, show_debit_card=True):
            response = self.submit_send_money_form(mocked_api_client, follow=True)
            self.assertOnPage(response, 'check_details')
            response = self.submit_check_details_form(mocked_api_client, update_data={
                'next': '',
            })
            self.assertRedirects(response, reverse_lazy('send_money:debit_card'),
                                 fetch_redirect_response=False)


class BankTransferViewTestCase(BaseTestCase):
    start_url = reverse_lazy('send_money:send_money_bank')
    url = reverse_lazy('send_money:bank_transfer')

    def bank_transfer_flow(self, mocked_api_client):
        return self.submit_send_money_form(
            mocked_api_client, replace_data={
                'prisoner_number': SAMPLE_FORM['prisoner_number'],
                'prisoner_dob': SAMPLE_FORM['prisoner_dob'],
            }, follow=True
        )

    def test_bank_transfer_page_not_directly_accessible(self):
        with reload_payment_urls(self, show_bank_transfer=True, show_debit_card=True):
            self.assertPageNotDirectlyAccessible()

    @mock.patch('send_money.utils.api_client')
    def test_bank_transfer_page_renders_prisoner_reference(self, mocked_api_client):
        with reload_payment_urls(self, show_bank_transfer=True, show_debit_card=True):
            response = self.bank_transfer_flow(mocked_api_client)
            bank_transfer_reference = 'A1231DE/04/10/1980'
            self.assertContains(response, bank_transfer_reference)
            self.assertEqual(response.context['bank_transfer_reference'],
                             bank_transfer_reference)

    @mock.patch('send_money.utils.api_client')
    def test_bank_transfer_page_renders_noms_account_details(self, mocked_api_client):
        with reload_payment_urls(self, show_bank_transfer=True, show_debit_card=True):
            response = self.bank_transfer_flow(mocked_api_client)
            keys = ['account_number', 'sort_code']
            for key in keys:
                value = response.context[key]
                self.assertTrue(value)
                self.assertContains(response, value)

    @mock.patch('send_money.utils.api_client')
    def test_bank_transfer_page_clears_session(self, mocked_api_client):
        with reload_payment_urls(self, show_bank_transfer=True, show_debit_card=True):
            self.bank_transfer_flow(mocked_api_client)
            for key in SendMoneyForm.get_field_names():
                self.assertNotIn(key, self.client.session)


class DebitCardViewTestCase(BaseTestCase):
    url = reverse_lazy('send_money:debit_card')
    payment_process_path = '/take'

    def test_debit_card_page_not_directly_accessible(self):
        with reload_payment_urls(self, show_debit_card=True):
            self.assertPageNotDirectlyAccessible()

    def test_debit_card_payment(self):
        with reload_payment_urls(self, show_debit_card=True):
            self.populate_session()
            with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
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
                response = self.client.get(self.url, follow=False)

                # check amount and service charge submitted to api
                self.assertEqual(json.loads(rsps.calls[1].request.body)['amount'], 1000)
                self.assertEqual(json.loads(rsps.calls[1].request.body)['service_charge'], 44)
                # check total charge submitted to govuk
                self.assertEqual(json.loads(rsps.calls[2].request.body)['amount'], 1044)

                self.assertRedirects(
                    response, govuk_url(self.payment_process_path),
                    fetch_redirect_response=False
                )

    def test_debit_card_payment_handles_api_errors(self):
        with reload_payment_urls(self, show_debit_card=True):
            self.populate_session()
            with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
                mock_auth(rsps)
                rsps.add(
                    rsps.POST,
                    api_url('/payments/'),
                    status=500,
                )
                with self.silence_logger():
                    response = self.client.get(self.url, follow=False)
                self.assertContains(response, 'We’re sorry, your payment could not be processed on this occasion')

    def test_debit_card_payment_handles_govuk_errors(self):
        with reload_payment_urls(self, show_debit_card=True):
            self.populate_session()
            with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
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
                with self.silence_logger():
                    response = self.client.get(self.url, follow=False)
                self.assertContains(response, 'We’re sorry, your payment could not be processed on this occasion')


class ConfirmationViewTestCase(BaseTestCase):
    url = reverse_lazy('send_money:confirmation')

    def test_confirmation_redirects_if_no_reference_param(self):
        with reload_payment_urls(self, show_debit_card=True):
            response = self.client.get(self.url, follow=False)
            self.assertRedirects(response, self.start_url)

    @override_settings(ENVIRONMENT='prod')  # because non-prod environments don't send to @outside.local
    def test_confirmation(self):
        with reload_payment_urls(self, show_debit_card=True):
            self.populate_session()
            with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
                ref = 'wargle-blargle'
                processor_id = '3'
                mock_auth(rsps)
                rsps.add(
                    rsps.GET,
                    api_url('/payments/%s/' % ref),
                    json={
                        'processor_id': processor_id,
                        'recipient_name': 'John',
                        'amount': 1000,
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
                    status=200,
                )
                response = self.client.get(
                    self.url, {'payment_ref': ref}, follow=False
                )
                self.assertContains(response, 'success')
                # check session is cleared
                self.assertEqual(None, self.client.session.get('prisoner_number'))
                self.assertEqual(None, self.client.session.get('amount'))

                self.assertEqual('Send money to a prisoner: your payment was successful', mail.outbox[0].subject)
                self.assertTrue('WARGLE-B' in mail.outbox[0].body)
                self.assertTrue('£10' in mail.outbox[0].body)

    def test_confirmation_handles_api_errors(self):
        with reload_payment_urls(self, show_debit_card=True):
            with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
                ref = 'wargle-blargle'
                processor_id = '3'
                mock_auth(rsps)
                rsps.add(
                    rsps.GET,
                    api_url('/payments/%s/' % ref),
                    json={
                        'processor_id': processor_id,
                        'recipient_name': 'John',
                        'amount': 1000,
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
                with self.silence_logger():
                    response = self.client.get(
                        self.url, {'payment_ref': ref}, follow=False
                    )
                self.assertContains(response, 'your payment could not be processed')

    def test_confirmation_handles_govuk_errors(self):
        with reload_payment_urls(self, show_debit_card=True):
            with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
                ref = 'wargle-blargle'
                processor_id = '3'
                mock_auth(rsps)
                rsps.add(
                    rsps.GET,
                    api_url('/payments/%s/' % ref),
                    json={
                        'processor_id': processor_id,
                        'recipient_name': 'John',
                        'amount': 1000,
                        'created': datetime.datetime.now().isoformat() + 'Z',
                    },
                    status=200,
                )
                rsps.add(
                    rsps.GET,
                    govuk_url('/payments/%s/' % processor_id),
                    status=500
                )
                with self.silence_logger():
                    response = self.client.get(
                        self.url, {'payment_ref': ref}, follow=False
                    )
                self.assertRedirects(response, reverse_lazy('send_money:send_money_debit'))


class PaymentOptionAvailabilityTestCase(SimpleTestCase):

    def assert_url_inaccessible(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_root_page_redirects_when_no_options_enabled(self):
        with reload_payment_urls(self):
            response = self.client.get('/')
            self.assertRedirects(response, reverse_lazy('submit_ticket'))

    def test_payment_pages_inaccessible_when_no_options_enabled(self):
        with reload_payment_urls(self):
            self.assert_url_inaccessible('/check-details')
            self.assert_url_inaccessible('/clear-session')
            self.assert_url_inaccessible('/bank-transfer')
            self.assert_url_inaccessible('/debit-card')
            self.assert_url_inaccessible('/confirmation')

    def test_bank_transfer_form_accessible_when_enabled(self):
        with reload_payment_urls(self, show_bank_transfer=True):
            response = self.client.get('/')

            self.assertContains(response, 'Prisoner number')
            self.assertContains(response, 'Prisoner date of birth')

            self.assertNotContains(response, 'Prisoner name')
            self.assertNotContains(response, 'Amount')
