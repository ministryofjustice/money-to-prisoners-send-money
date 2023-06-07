from http import HTTPStatus
import json
from unittest import mock
from xml.etree import ElementTree

from django.conf import settings
from django.test import override_settings, SimpleTestCase
from django.urls import reverse, reverse_lazy
from django.utils.cache import get_max_age
from django.utils.translation import override as override_lang
from mtp_common.analytics import AnalyticsPolicy
from mtp_common.test_utils import silence_logger
import responses

from send_money.tests import (
    BaseTestCase,
    mock_auth,
    patch_notifications,
    patch_gov_uk_pay_availability_check
)


@patch_notifications()
@patch_gov_uk_pay_availability_check()
class PerformanceCookiesTestCase(BaseTestCase):
    test_page = reverse_lazy('send_money:user_agreement')

    def test_prompt_visible_without_cookie(self):
        response = self.client.get(self.test_page)
        self.assertContains(response, 'govuk-cookie-banner')

    def test_prompt_not_visible_when_cookie_policy_is_set(self):
        self.client.cookies[AnalyticsPolicy.cookie_name] = '{"usage":true}'
        response = self.client.get(self.test_page)
        self.assertNotContains(response, 'govuk-cookie-banner')

        self.client.cookies[AnalyticsPolicy.cookie_name] = '{"usage":false}'
        response = self.client.get(self.test_page)
        self.assertNotContains(response, 'govuk-cookie-banner')

    @override_settings(GOOGLE_ANALYTICS_ID='ABC123')
    def test_performance_analytics_off_by_default(self):
        response = self.client.get(self.test_page)
        self.assertNotContains(response, 'ABC123')
        self.assertNotContains(response, 'govuk_shared.send')

    @override_settings(GOOGLE_ANALYTICS_ID='ABC123')
    def test_performace_cookies_can_be_accepted(self):
        response = self.client.post(reverse('cookies'), data={'accept_cookies': 'yes'})
        cookie = response.cookies.get(AnalyticsPolicy.cookie_name).value
        self.assertDictEqual(json.loads(cookie), {'usage': True})
        response = self.client.get(self.test_page)
        self.assertNotContains(response, 'govuk-cookie-banner')
        self.assertContains(response, 'ABC123')

    @override_settings(GOOGLE_ANALYTICS_ID='ABC123')
    def test_performace_cookies_can_be_rejected(self):
        response = self.client.post(reverse('cookies'), data={'accept_cookies': 'no'})
        cookie = response.cookies.get(AnalyticsPolicy.cookie_name).value
        self.assertDictEqual(json.loads(cookie), {'usage': False})
        response = self.client.get(self.test_page)
        self.assertNotContains(response, 'govuk-cookie-banner')
        self.assertNotContains(response, 'ABC123')

    @override_settings(GOOGLE_ANALYTICS_ID='ABC123')
    def test_cookie_prompt_safely_redirects_back(self):
        for safe_page in ['send_money:user_agreement', 'send_money:choose_method', 'help_area:help', 'terms']:
            response = self.client.post(reverse('cookies'), data={
                'accept_cookies': 'yes',
                'next': reverse(safe_page),
            }, follow=True)
            self.assertOnPage(response, safe_page.split(':')[-1])

        response = self.client.post(reverse('cookies'), data={
            'accept_cookies': 'yes',
            'next': 'http://example.com/',
        }, follow=True)
        self.assertOnPage(response, 'cookies')


class SitemapTestCase(BaseTestCase):
    name_space = {
        's': 'http://www.sitemaps.org/schemas/sitemap/0.9',
        'x': 'http://www.w3.org/1999/xhtml',
    }

    def assertAbsoluteURL(self, url):  # noqa: N802
        self.assertIn(url.split(':', 1)[0], ('http', 'https'), msg='URL is not absolute')

    def get_sitemap(self):
        response = self.client.get(reverse('sitemap_xml'))
        return ElementTree.fromstring(response.content.decode(response.charset))

    def test_sitemap_with_multiple_languages(self):
        language_codes = set(lang[0] for lang in settings.LANGUAGES)
        with self.settings(SHOW_LANGUAGE_SWITCH=True):
            for url_element in self.get_sitemap():
                loc_elements = url_element.findall('s:loc', self.name_space)
                self.assertEqual(len(loc_elements), 1)
                url = loc_elements[0].findtext('.').strip()
                self.assertAbsoluteURL(url)

                link_elements = url_element.findall('x:link', self.name_space)
                for link_element in link_elements:
                    self.assertIn(link_element.attrib['hreflang'], language_codes)
                    self.assertAbsoluteURL(link_element.attrib['href'])

    def test_sitemap_with_enlish_only(self):
        with self.settings(SHOW_LANGUAGE_SWITCH=False):
            for url_element in self.get_sitemap():
                loc_elements = url_element.findall('s:loc', self.name_space)
                self.assertEqual(len(loc_elements), 1)
                url = loc_elements[0].findtext('.').strip()
                self.assertAbsoluteURL(url)

                link_elements = url_element.findall('x:link', self.name_space)
                self.assertFalse(link_elements)


class PlainViewTestCase(BaseTestCase):
    @mock.patch('help_area.views.get_api_session')
    def test_plain_views_are_cacheable(self, mocked_api_session):
        mocked_api_session().get().json.return_value = {
            'count': 1,
            'results': [{'nomis_id': 'AAA', 'short_name': 'Prison', 'name': 'HMP Prison'}],
        }
        view_names = [
            'help_area:help', 'help_area:help-new-payment', 'help_area:help-sent-payment',
            'help_area:prison_list',
            'terms', 'privacy',
            'js-i18n',
            'sitemap_xml',
            'accessibility'
        ]
        for view_name in view_names:
            response = self.client.get(reverse(view_name))
            self.assertGreaterEqual(get_max_age(response), 3600, msg=f'{view_name} should be cacheable')
            with override_lang('cy'):
                response = self.client.get(reverse(view_name))
                self.assertGreaterEqual(get_max_age(response), 3600, msg=f'{view_name} should be cacheable')

    def test_feedback_views_are_uncacheable(self):
        view_names = [
            'help_area:submit_ticket', 'help_area:feedback_success',
            'healthcheck_json', 'ping_json',
        ]
        with responses.RequestsMock() as rsps:
            rsps.add(rsps.GET, '%s/%s' % (settings.API_URL, 'healthcheck.json'), json={})
            for view_name in view_names:
                response = self.client.get(reverse(view_name))
                self.assertResponseNotCacheable(response)


class PerformancePlatformTestCase(SimpleTestCase):

    def setUp(self):
        # NOTE: The structure of the API response is the same (e.g. with headers/results) but
        # the headers and obviously the data itself are not.
        # This is a simpler response to test conversion to CSV, caching, filtering etc...
        self.headers = {
            'week_commencing': 'Week commencing',
            'credits_total': 'Transactions – total',
        }
        api_response = {
            'headers': self.headers,
            'results': [
                {'week_commencing': '2021-06-07', 'credits_total': 100},
                {'week_commencing': '2021-06-14'},  # Missing value (although it shouldn't happen)
                {'credits_total': 200, 'week_commencing': '2021-06-21'},  # Different order
            ]
        }

        with responses.RequestsMock() as rsps:
            mock_auth(rsps)
            rsps.add(rsps.GET, f'{settings.API_URL}/performance/data/', json=api_response)

            self.response = self.client.get(reverse_lazy('performance_data_csv'))

    def test_responds_200(self):
        self.assertEqual(self.response.status_code, HTTPStatus.OK)

    def test_csv_response_type(self):
        self.assertEqual(self.response['Content-Type'], 'text/csv; charset=UTF-8')
        self.assertEqual(self.response['Content-Disposition'], 'attachment; filename="performance-data.csv"')

    def test_csv_response_format(self):
        csv_content = self.response.content.decode('utf8')
        expected_csv_content = 'Week commencing,Transactions – total\r\n2021-06-07,100\r\n2021-06-14,\r\n2021-06-21,200\r\n'  # noqa: E501
        self.assertEqual(expected_csv_content, csv_content)

    def test_caching(self):
        self.assertTrue(self.response.has_header('Cache-Control'), msg='response has no Cache-Control header')
        self.assertIn('public', self.response['Cache-Control'], msg='response is private')

        expected_max_age = 7 * 24 * 60 * 60  # 7 days in seconds
        self.assertGreaterEqual(get_max_age(self.response), expected_max_age, msg='max-age is less than a week')

    def test_invalid_date_params(self):
        with responses.RequestsMock(), silence_logger(name='django.request'):
            response = self.client.get(reverse_lazy('performance_data_csv') + '?from=invalid')
            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
            self.assertIn('Date "invalid" could not be parsed - use YYYY-MM-DD format', response.json()['errors'])
            self.assertEqual(0, get_max_age(response))

        with responses.RequestsMock(), silence_logger(name='django.request'):
            response = self.client.get(reverse_lazy('performance_data_csv') + '?from=2021-01-01&to=invalid')
            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
            self.assertIn('Date "invalid" could not be parsed - use YYYY-MM-DD format', response.json()['errors'])
            self.assertEqual(0, get_max_age(response))

    def test_date_filtering(self):
        with self.subTest('only "from" query parameter passed'):
            from_param = '2021-06-10'
            api_response = {
                'headers': self.headers,
                'results': [
                    {'week_commencing': '2021-06-28', 'credits_total': 100},
                    {'week_commencing': '2021-07-05', 'credits_total': 200},
                ]
            }
            with responses.RequestsMock() as rsps:
                mock_auth(rsps)
                rsps.add(rsps.GET, f'{settings.API_URL}/performance/data/', json=api_response)

                query_params = f'?from={from_param}'
                response = self.client.get(reverse_lazy('performance_data_csv') + query_params)

                self.assertEqual(response.status_code, HTTPStatus.OK)
                self.assertEqual(response['Content-Type'], 'text/csv; charset=UTF-8')
                csv = response.content.decode('utf8')
                self.assertEqual(csv, 'Week commencing,Transactions – total\r\n2021-06-28,100\r\n2021-07-05,200\r\n')

                api_request = rsps.calls[1].request
                self.assertDictEqual(api_request.params, {'week__gte': from_param})

        with self.subTest('both "from" and "to" query parameters passed'):
            from_param = '2021-06-10'
            to_param = '2021-07-01'
            api_response = {
                'headers': self.headers,
                'results': [
                    {'week_commencing': '2021-06-28', 'credits_total': 100},
                ]
            }
            with responses.RequestsMock() as rsps:
                mock_auth(rsps)
                rsps.add(rsps.GET, f'{settings.API_URL}/performance/data/', json=api_response)

                query_params = f'?from={from_param}&to={to_param}'
                response = self.client.get(reverse_lazy('performance_data_csv') + query_params)

                self.assertEqual(response.status_code, HTTPStatus.OK)
                self.assertEqual(response['Content-Type'], 'text/csv; charset=UTF-8')
                csv = response.content.decode('utf8')
                self.assertEqual(csv, 'Week commencing,Transactions – total\r\n2021-06-28,100\r\n')

                api_request = rsps.calls[1].request
                self.assertDictEqual(api_request.params, {'week__gte': from_param, 'week__lt': to_param})
