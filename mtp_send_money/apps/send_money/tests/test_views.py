from unittest import mock

from django.core.urlresolvers import reverse
from django.test.testcases import SimpleTestCase
from requests import ConnectionError

from send_money.forms import PaymentMethod, SendMoneyForm


class BaseTestCase(SimpleTestCase):
    send_money_url = reverse('send_money:send_money')

    def assertPageNotDirectlyAccessible(self):  # noqa
        response = self.client.get(self.url)
        self.assertRedirects(response, self.send_money_url)

    def submit_send_money_form(self, mocked_api_client, data=None, follow=False):
        prisoner_details = {
            'prisoner_number': 'A1231DE',
            'prisoner_dob': '1980-10-04',
        }
        mocked_client = mocked_api_client.get_connection()
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

    @mock.patch('send_money.forms.api_client')
    def test_send_money_page_previews_form(self, mocked_api_client):
        response = self.submit_send_money_form(mocked_api_client)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!-- send_money.preview -->', response.content)
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
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Incorrect prisoner number format', response.content)
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
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'This field is required', response.content)
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
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No prisoner was found with given number and date of birth', response.content)
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
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Could not connect to service, please try again later', response.content)
        form = response.context['form']
        self.assertTrue(form.errors)

    @mock.patch('send_money.forms.api_client')
    def test_send_money_page_allows_changing_form(self, mocked_api_client):
        response = self.submit_send_money_form(mocked_api_client)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!-- send_money.preview -->', response.content)
        response = self.submit_send_money_form(mocked_api_client, {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.debit_card,
            'change': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!-- send_money.form -->', response.content)

    @mock.patch('send_money.forms.api_client')
    def test_send_money_page_can_proceed_to_debit_card(self, mocked_api_client):
        response = self.submit_send_money_form(mocked_api_client)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!-- send_money.preview -->', response.content)
        response = self.submit_send_money_form(mocked_api_client, {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.debit_card,
            'next': '',
        })
        self.assertRedirects(response, reverse('send_money:debit_card'))

    @mock.patch('send_money.forms.api_client')
    def test_send_money_page_can_proceed_to_bank_transfer(self, mocked_api_client):
        response = self.submit_send_money_form(mocked_api_client, {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.bank_transfer,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!-- send_money.preview -->', response.content)
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
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!-- send_money.preview -->', response.content)
        response = self.submit_send_money_form(mocked_api_client, {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.bank_transfer,
            'next': '',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!-- bank_transfer -->', response.content)
        return response

    def test_bank_transfer_page_not_directly_accessible(self):
        self.assertPageNotDirectlyAccessible()

    @mock.patch('send_money.forms.api_client')
    def test_bank_transfer_page_renders_prisoner_reference(self, mocked_api_client):
        response = self.bank_transfer_flow(mocked_api_client)
        bank_transfer_reference = 'A1231DE 04/10/1980'
        self.assertIn(bank_transfer_reference.encode('utf-8'), response.content)
        self.assertEqual(response.context['bank_transfer_reference'],
                         bank_transfer_reference)

    @mock.patch('send_money.forms.api_client')
    def test_bank_transfer_page_renders_noms_account_details(self, mocked_api_client):
        response = self.bank_transfer_flow(mocked_api_client)
        keys = ['payable_to', 'account_number', 'sort_code']
        for key in keys:
            value = response.context[key]
            self.assertTrue(value)
            self.assertIn(value.encode('utf-8'), response.content)

    @mock.patch('send_money.forms.api_client')
    def test_bank_transfer_page_clears_session(self, mocked_api_client):
        self.bank_transfer_flow(mocked_api_client)
        for key in SendMoneyForm.get_field_names():
            self.assertNotIn(key, self.client.session)


class CardPaymentViewTestCase(BaseTestCase):
    url = reverse('send_money:debit_card')

    def debit_card_flow(self, mocked_api_client):
        response = self.submit_send_money_form(mocked_api_client)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!-- send_money.preview -->', response.content)
        response = self.submit_send_money_form(mocked_api_client, {
            'prisoner_name': 'John Smith',
            'amount': '10.00',
            'payment_method': PaymentMethod.debit_card,
            'next': '',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!-- debit_card -->', response.content)

    def test_debit_card_page_not_directly_accessible(self):
        self.assertPageNotDirectlyAccessible()

    @mock.patch('send_money.forms.api_client')
    def test_debit_card_page_renders(self, mocked_api_client):
        self.debit_card_flow(mocked_api_client)
        # NB: nothing else to test yet


class ConfirmationViewTestCase(BaseTestCase):
    url = reverse('send_money:confirmation')

    def test_confirmation_page_not_directly_accessible(self):
        self.assertPageNotDirectlyAccessible()

    def test_confirmation_page_clears_session(self):
        # NB: can't reach this page properly yet
        pass

    # NB: nothing else to test yet
