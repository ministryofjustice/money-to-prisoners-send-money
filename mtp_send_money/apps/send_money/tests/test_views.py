from unittest import mock

from django.conf import settings
from django.core.urlresolvers import reverse
from django.test.testcases import SimpleTestCase
from requests import ConnectionError
import responses

from send_money.forms import PaymentMethod, SendMoneyForm
from send_money.utils import govuk_url, api_url
from .test_utils import mock_auth


class BaseTestCase(SimpleTestCase):
    send_money_url = reverse('send_money:send_money')

    def populate_session(
        self,
        prisoner_name='John Smith',
        prisoner_number='A1231DE',
        prisoner_dob='1980-10-04',
        amount='10.00'
    ):
        s = self.client.session
        s['prisoner_name'] = prisoner_name
        s['prisoner_number'] = prisoner_number
        s['prisoner_dob'] = prisoner_dob
        s['amount'] = amount
        s['payment_method'] = PaymentMethod.debit_card.name
        s.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = s.session_key

    def assertPageNotDirectlyAccessible(self):  # noqa
        response = self.client.get(self.url)
        self.assertRedirects(response, self.send_money_url)

    def submit_send_money_form(self, mocked_api_client, data=None, follow=False):
        prisoner_details = {
            'prisoner_number': 'A1231DE',
            'prisoner_dob': '1980-10-04',
        }
        mocked_client = mocked_api_client.get_authenticated_connection()
        mocked_client.prisoner_validity().get.return_value = {
            'count': 1,
            'results': [prisoner_details]
        }
        data = data or {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.debit_card,
        }
        data.update(prisoner_details)
        return self.client.post(self.send_money_url, data=data, follow=follow)


class SendMoneyViewTestCase(BaseTestCase):
    url = BaseTestCase.send_money_url

    def test_send_money_page_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    @mock.patch('send_money.utils.api_client')
    def test_send_money_page_previews_form(self, mocked_api_client):
        response = self.submit_send_money_form(mocked_api_client)
        self.assertContains(response, '<!-- send_money.preview -->')
        form = response.context['form']
        self.assertFalse(form.errors)

    @mock.patch('send_money.forms.SendMoneyForm.check_prisoner_validity')
    def test_send_money_page_displays_errors_for_invalid_prisoner_number(self, mocked_check_prisoner_validity):
        response = self.client.post(self.url, data={
            'prisoner_name': 'John Smith',
            'prisoner_number': 'a1231a1',
            'prisoner_dob': '1980-10-04',
            'amount': '10.00',
            'payment_method': PaymentMethod.debit_card,
        })
        self.assertContains(response, 'Incorrect prisoner number format')
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertEqual(mocked_check_prisoner_validity.call_count, 0)

    @mock.patch('send_money.forms.SendMoneyForm.check_prisoner_validity')
    def test_send_money_page_displays_errors_for_invalid_prisoner_dob(self, mocked_check_prisoner_validity):
        response = self.client.post(self.url, data={
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1231DE',
            'amount': '10.00',
            'payment_method': PaymentMethod.debit_card,
        })
        self.assertContains(response, 'This field is required')
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertEqual(mocked_check_prisoner_validity.call_count, 0)

    @mock.patch('send_money.forms.SendMoneyForm.check_prisoner_validity')
    def test_send_money_page_displats_errors_for_invalid_prisoner_details(self, mocked_check_prisoner_validity):
        mocked_check_prisoner_validity.return_value = False
        response = self.client.post(self.url, data={
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1231DE',
            'prisoner_dob': '1980-10-04',
            'amount': '10.00',
            'payment_method': PaymentMethod.debit_card,
        })
        self.assertContains(response, 'No prisoner was found with given number and date of birth')
        form = response.context['form']
        self.assertTrue(form.errors)

    @mock.patch('send_money.forms.SendMoneyForm.check_prisoner_validity')
    def test_send_money_page_displays_errors_for_dropped_api_connection(self, mocked_check_prisoner_validity):
        mocked_check_prisoner_validity.side_effect = ConnectionError
        response = self.client.post(self.url, data={
            'prisoner_name': 'John Smith',
            'prisoner_number': 'A1231DE',
            'prisoner_dob': '1980-10-04',
            'amount': '10.00',
            'payment_method': PaymentMethod.debit_card,
        })
        self.assertContains(response, 'Could not connect to service, please try again later')
        form = response.context['form']
        self.assertTrue(form.errors)

    @mock.patch('send_money.utils.api_client')
    def test_send_money_page_allows_changing_form(self, mocked_api_client):
        response = self.submit_send_money_form(mocked_api_client)
        self.assertContains(response, '<!-- send_money.preview -->')
        response = self.submit_send_money_form(mocked_api_client, {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.debit_card,
            'change': '',
        })
        self.assertContains(response, '<!-- send_money.form -->')

    @mock.patch('send_money.utils.api_client')
    def test_send_money_page_can_proceed_to_debit_card(self, mocked_api_client):
        response = self.submit_send_money_form(mocked_api_client)
        self.assertContains(response, '<!-- send_money.preview -->')
        response = self.submit_send_money_form(mocked_api_client, {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.debit_card,
            'next': '',
        })
        self.assertRedirects(
            response, reverse('send_money:debit_card'), fetch_redirect_response=False
        )

    @mock.patch('send_money.utils.api_client')
    def test_send_money_page_can_proceed_to_bank_transfer(self, mocked_api_client):
        response = self.submit_send_money_form(mocked_api_client, {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.bank_transfer,
        })
        self.assertContains(response, '<!-- send_money.preview -->')
        response = self.submit_send_money_form(mocked_api_client, {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.bank_transfer,
            'next': '',
        })
        self.assertRedirects(response, reverse('send_money:bank_transfer'))


class BankTransferViewTestCase(BaseTestCase):
    url = reverse('send_money:bank_transfer')

    def bank_transfer_flow(self, mocked_api_client):
        response = self.submit_send_money_form(mocked_api_client, {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.bank_transfer,
        })
        self.assertContains(response, '<!-- send_money.preview -->')
        response = self.submit_send_money_form(mocked_api_client, {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.bank_transfer,
            'next': '',
        }, follow=True)
        self.assertContains(response, '<!-- bank_transfer -->')
        return response

    def test_bank_transfer_page_not_directly_accessible(self):
        self.assertPageNotDirectlyAccessible()

    @mock.patch('send_money.utils.api_client')
    def test_bank_transfer_page_renders_prisoner_reference(self, mocked_api_client):
        response = self.bank_transfer_flow(mocked_api_client)
        bank_transfer_reference = 'A1231DE 04/10/1980'
        self.assertContains(response, bank_transfer_reference)
        self.assertEqual(response.context['bank_transfer_reference'],
                         bank_transfer_reference)

    @mock.patch('send_money.utils.api_client')
    def test_bank_transfer_page_renders_noms_account_details(self, mocked_api_client):
        response = self.bank_transfer_flow(mocked_api_client)
        keys = ['payable_to', 'account_number', 'sort_code']
        for key in keys:
            value = response.context[key]
            self.assertTrue(value)
            self.assertContains(response, value)

    @mock.patch('send_money.utils.api_client')
    def test_bank_transfer_page_clears_session(self, mocked_api_client):
        self.bank_transfer_flow(mocked_api_client)
        for key in SendMoneyForm.get_field_names():
            self.assertNotIn(key, self.client.session)


class DebitCardViewTestCase(BaseTestCase):
    url = reverse('send_money:debit_card')
    payment_process_path = '/take'

    def test_debit_card_page_not_directly_accessible(self):
        self.assertPageNotDirectlyAccessible()

    def test_debit_card_payment(self):
        self.populate_session()
        with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
            mock_auth(rsps)
            rsps.add(
                rsps.POST,
                api_url('/send_money/transactions/'),
                json={'id': 3},
                status=201,
            )
            rsps.add(
                rsps.POST,
                govuk_url('/payments/'),
                json={
                    'links': [
                        {'rel': 'next_url', 'href': govuk_url(self.payment_process_path)}
                    ]
                },
                status=201
            )
            response = self.client.get(self.url, follow=False)
            self.assertRedirects(
                response, govuk_url(self.payment_process_path),
                fetch_redirect_response=False
            )

    def test_debit_card_payment_handles_api_errors(self):
        self.populate_session()
        with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
            mock_auth(rsps)
            rsps.add(
                rsps.POST,
                api_url('/send_money/transactions/'),
                status=500,
            )
            response = self.client.get(self.url, follow=False)
            self.assertContains(response, 'Sorry, we are unable to take your payment.')

    def test_debit_card_payment_handles_govuk_errors(self):
        self.populate_session()
        with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
            mock_auth(rsps)
            rsps.add(
                rsps.POST,
                api_url('/send_money/transactions/'),
                json={'id': 3},
                status=201,
            )
            rsps.add(
                rsps.POST,
                govuk_url('/payments/'),
                status=500
            )
            response = self.client.get(self.url, follow=False)
            self.assertContains(response, 'Sorry, we are unable to take your payment.')


class ConfirmationViewTestCase(BaseTestCase):
    url = reverse('send_money:confirmation')

    def test_confirmation_redirects_if_no_reference_param(self):
        response = self.client.get(self.url, follow=False)
        self.assertRedirects(response, self.send_money_url)

    def test_confirmation(self):
        self.populate_session()
        with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
            ref = '3'
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % ref),
                json={
                    'status': 'SUCCEEDED'
                },
                status=200
            )
            mock_auth(rsps)
            rsps.add(
                rsps.POST,
                api_url('/send_money/transactions/%s/' % ref),
                status=200,
            )
            response = self.client.get(
                self.url, {'paymentReference': ref}, follow=False
            )
            self.assertContains(response, 'SUCCESS')
            # check session is cleared
            self.assertEqual(None, self.client.session.get('prisoner_number'))
            self.assertEqual(None, self.client.session.get('amount'))

    def test_confirmation_handles_api_errors(self):
        with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
            ref = '3'
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % ref),
                json={
                    'status': 'SUCCEEDED'
                },
                status=200
            )
            mock_auth(rsps)
            rsps.add(
                rsps.POST,
                api_url('/send_money/transactions/%s/' % ref),
                status=500,
            )
            response = self.client.get(
                self.url, {'paymentReference': ref}, follow=False
            )
            self.assertContains(response, 'FAILURE')

    def test_confirmation_handles_govuk_errors(self):
        with responses.RequestsMock() as rsps, self.settings(GOVUK_PAY_URL='http://payment.gov.uk'):
            ref = '3'
            rsps.add(
                rsps.GET,
                govuk_url('/payments/%s/' % ref),
                status=500
            )
            response = self.client.get(
                self.url, {'paymentReference': ref}, follow=False
            )
            self.assertContains(response, 'FAILURE')
