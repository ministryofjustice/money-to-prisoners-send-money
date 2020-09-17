import json
from unittest import mock
from xml.etree import ElementTree

from django.conf import settings
from django.template import Context, Template
from django.test import override_settings
from django.urls import reverse
from django.utils.cache import get_max_age
from django.utils.translation import override as override_lang
from mtp_common.analytics import AnalyticsPolicy
import responses

from send_money.tests import BaseTestCase, patch_notifications, patch_gov_uk_pay_availability_check


@patch_notifications()
@patch_gov_uk_pay_availability_check()
class PerformanceCookiesTestCase(BaseTestCase):
    def test_prompt_visible_without_cookie(self):
        response = self.client.get(reverse('send_money:choose_method'))
        self.assertContains(response, 'mtp-cookie-prompt')

    def test_prompt_not_visible_when_cookie_policy_is_set(self):
        self.client.cookies[AnalyticsPolicy.cookie_name] = '{"usage":true}'
        response = self.client.get(reverse('send_money:choose_method'))
        self.assertNotContains(response, 'mtp-cookie-prompt')

        self.client.cookies[AnalyticsPolicy.cookie_name] = '{"usage":false}'
        response = self.client.get(reverse('send_money:choose_method'))
        self.assertNotContains(response, 'mtp-cookie-prompt')

    @override_settings(GOOGLE_ANALYTICS_ID='ABC123')
    def test_performance_analytics_off_by_default(self):
        response = self.client.get(reverse('send_money:choose_method'))
        self.assertNotContains(response, 'ABC123')
        self.assertNotContains(response, 'govuk_shared.send')

    @override_settings(GOOGLE_ANALYTICS_ID='ABC123')
    def test_performace_cookies_can_be_accepted(self):
        response = self.client.post(reverse('cookies'), data={'accept_cookies': 'yes'})
        cookie = response.cookies.get(AnalyticsPolicy.cookie_name).value
        self.assertDictEqual(json.loads(cookie), {'usage': True})
        response = self.client.get(reverse('send_money:choose_method'))
        self.assertNotContains(response, 'mtp-cookie-prompt')
        self.assertContains(response, 'ABC123')

    @override_settings(GOOGLE_ANALYTICS_ID='ABC123')
    def test_performace_cookies_can_be_rejected(self):
        response = self.client.post(reverse('cookies'), data={'accept_cookies': 'no'})
        cookie = response.cookies.get(AnalyticsPolicy.cookie_name).value
        self.assertDictEqual(json.loads(cookie), {'usage': False})
        response = self.client.get(reverse('send_money:choose_method'))
        self.assertNotContains(response, 'mtp-cookie-prompt')
        self.assertNotContains(response, 'ABC123')

    @override_settings(GOOGLE_ANALYTICS_ID='ABC123', GOOGLE_ANALYTICS_GDS_ID='GDS321')
    def test_gds_performance_analytics_off_by_default(self):
        response = self.client.get(reverse('send_money:choose_method'))
        self.assertNotContains(response, 'GDS321')
        self.assertNotContains(response, 'govuk_shared.send')

    @override_settings(GOOGLE_ANALYTICS_ID='ABC123', GOOGLE_ANALYTICS_GDS_ID='GDS321')
    def test_gds_performance_analytics_can_be_accepted(self):
        self.client.post(reverse('cookies'), data={'accept_cookies': 'yes'})
        response = self.client.get(reverse('send_money:choose_method'))
        self.assertContains(response, 'GDS321')
        self.assertContains(response, 'govuk_shared.send')

    @override_settings(GOOGLE_ANALYTICS_ID='ABC123')
    def test_cookie_prompt_safely_redirects_back(self):
        for safe_page in ['send_money:choose_method', 'help_area:help']:
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


class TemplateTestCase(BaseTestCase):
    def test_counter(self):
        template = Template("""
            {% load send_money %}
            {% create_counter 'test' %}
            {% increment_counter 'test' %}
        """)
        html = template.render(Context()).strip()
        self.assertEqual(html, '1')

        template = Template("""
            {% load send_money %}
            {% create_counter 'test' %}
            {% increment_counter 'test' %},{% increment_counter 'test' %},{% increment_counter 'test' %}
        """)
        html = template.render(Context()).strip()
        self.assertEqual(html, '1,2,3')

        template = Template("""
            {% load send_money %}
            {% create_counter a %}
            {% create_counter b %}
            {% increment_counter a %},{% increment_counter a %},{% increment_counter b %},{% increment_counter a %}
        """)
        html = template.render(Context({'a': 'test1', 'b': 'test2'})).strip()
        self.assertEqual(html, '1,2,1,3')
