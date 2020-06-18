import datetime
from unittest import mock

from django.conf import settings
from django.urls import reverse, reverse_lazy
import responses

from send_money.tests import BaseTestCase


class ContactUsTestCase(BaseTestCase):
    contact_us_url = reverse_lazy('help_area:submit_ticket')
    sample_submission = {
        'ticket_content': 'I’d like some help',
        'contact_email': 's.smith@localhost',
    }

    contact_us_new_payment_url = reverse_lazy('help_area:contact-us-new-payment')
    new_payment_sample_submission = {
        'ticket_content': 'I’d like some help',
        'contact_name': 'Ms Smith',
        'contact_email': 's.smith@localhost',
        'payment_method': 'debit_card',
        'prisoner_number': 'A1401AE',
        'prisoner_dob_0': '21',
        'prisoner_dob_1': '1',
        'prisoner_dob_2': '1989',
    }

    contact_us_sent_payment_url = reverse_lazy('help_area:contact-us-sent-payment')
    sent_payment_sample_submission = {
        'ticket_content': 'I’d like some help',
        'contact_name': 'Ms Smith',
        'contact_email': 's.smith@localhost',
        'payment_method': 'debit_card',
        'prisoner_number': 'A1401AE',
        'prisoner_dob_0': '21',
        'prisoner_dob_1': '1',
        'prisoner_dob_2': '1989',
        'amount': '35.10',
        'payment_date_0': '8',
        'payment_date_1': '6',
        'payment_date_2': '2020',
    }

    forms = {
        'generic': (contact_us_url, sample_submission),
        'new_payment': (contact_us_new_payment_url, new_payment_sample_submission),
        'sent_payment': (contact_us_sent_payment_url, sent_payment_sample_submission),
    }

    def test_legacy_url_name(self):
        url = reverse('submit_ticket')
        self.assertTrue(url, msg='Unnamespaced `submit_ticket` url name should exist for mtp-common compatibility')

    def test_sample_submissions(self):
        for conf in self.forms.values():
            url, sample_submission = conf
            with responses.RequestsMock() as rsps:
                rsps.add(rsps.POST, f'{settings.ZENDESK_BASE_URL}/api/v2/tickets.json', '{}')
                response = self.client.post(url, data=sample_submission, follow=True)
            self.assertOnPage(response, 'feedback_success')

    def test_honeypot(self):
        for name, conf in self.forms.items():
            url, sample_submission = conf
            data = dict(sample_submission, subject='Payment issue')
            with responses.RequestsMock():
                response = self.client.post(url, data=data)
            self.assertContains(response, 'The service is currently unavailable',
                                msg_prefix=f'{name} contact form honeypot failed')

    def test_all_fields_required(self):
        for name, conf in self.forms.items():
            url, sample_submission = conf
            fields = set(sample_submission.keys())
            for field in fields:
                data = dict(sample_submission)
                data.pop(field)
                with responses.RequestsMock():
                    response = self.client.post(url, data=data)
                self.assertContains(response, 'required',
                                    msg_prefix=f'{name} contact form should require {field}')

    def test_future_payment_date_in_sent_payment_ticket(self):
        url = self.contact_us_sent_payment_url
        data = dict(self.sent_payment_sample_submission)
        data['payment_date_0'] = '18'
        data['payment_date_1'] = '6'
        data['payment_date_2'] = '2020'
        with responses.RequestsMock(), mock.patch('help_area.forms.timezone') as timezone:
            timezone.now().date.return_value = datetime.date(2020, 6, 17)
            response = self.client.post(url, data=data)
        self.assertContains(response, 'Date can’t be in the future')

    @mock.patch('zendesk_tickets.client.create_ticket')
    def test_fields_in_new_payment_ticket(self, mocked_create_ticket):
        self.client.post(self.contact_us_new_payment_url, data=self.new_payment_sample_submission)
        args, kwargs = mocked_create_ticket.call_args
        ticket_body = args[2]
        self.assertIn('I’d like some help', ticket_body)
        self.assertIn('Ms Smith', ticket_body)
        self.assertIn('s.smith@localhost', ticket_body)
        self.assertIn('A1401AE', ticket_body)
        self.assertIn('21/01/1989', ticket_body)
        self.assertIn('Debit card', ticket_body)

    @mock.patch('zendesk_tickets.client.create_ticket')
    def test_fields_in_sent_payment_ticket(self, mocked_create_ticket):
        self.client.post(self.contact_us_sent_payment_url, data=self.sent_payment_sample_submission)
        args, kwargs = mocked_create_ticket.call_args
        ticket_body = args[2]
        self.assertIn('I’d like some help', ticket_body)
        self.assertIn('Ms Smith', ticket_body)
        self.assertIn('s.smith@localhost', ticket_body)
        self.assertIn('A1401AE', ticket_body)
        self.assertIn('21/01/1989', ticket_body)
        self.assertIn('Debit card', ticket_body)
        self.assertIn('£35.10', ticket_body)
        self.assertIn('08/06/2020', ticket_body)
