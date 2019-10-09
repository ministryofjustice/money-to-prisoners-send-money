from unittest import mock
from xml.etree import ElementTree

from django.conf import settings
from django.urls import reverse
from django.utils.cache import get_max_age
from django.utils.translation import override as override_lang
import responses

from send_money.tests import BaseTestCase, mock_auth
from send_money.utils import api_url


class SitemapTestCase(BaseTestCase):
    name_space = {
        's': 'http://www.sitemaps.org/schemas/sitemap/0.9',
        'x': 'http://www.w3.org/1999/xhtml',
    }

    def assertAbsoluteURL(self, url):  # noqa
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


class PrisonList(BaseTestCase):
    def test_prison_list(self):
        with responses.RequestsMock() as rsps, \
                self.settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}):
            mock_auth(rsps)
            rsps.add(
                rsps.GET,
                api_url('/prisons/'),
                json={
                    'count': 2,
                    'results': [
                        {
                            'nomis_id': 'BBB',
                            'short_name': 'Prison 1',
                            'name': 'YOI Prison 1',
                        },
                        {
                            'nomis_id': 'AAA',
                            'short_name': 'Prison 2',
                            'name': 'HMP Prison 2',
                        },
                    ],
                },
            )
            response = self.client.get(reverse('send_money:prison_list'))
            self.assertIn('exclude_empty_prisons=True', rsps.calls[-1].request.url)
        self.assertContains(response, 'Prison 1')
        response = response.content.decode(response.charset)
        self.assertIn('Prison 2', response)
        self.assertLess(response.index('Prison 1'), response.index('Prison 2'))


class PlainViewTestCase(BaseTestCase):
    @mock.patch('send_money.views_misc.get_api_session')
    def test_plain_views_are_cacheable(self, mocked_api_session):
        mocked_api_session().get().json.return_value = {
            'count': 1,
            'results': [{'nomis_id': 'AAA', 'short_name': 'Prison', 'name': 'HMP Prison'}],
        }
        view_names = [
            'send_money:help', 'send_money:prison_list',
            'send_money:help_bank_transfer', 'send_money:help_delays', 'send_money:help_transfered',
            'terms', 'privacy',
            'js-i18n',
            'sitemap_xml',
        ]
        for view_name in view_names:
            response = self.client.get(reverse(view_name))
            self.assertGreaterEqual(get_max_age(response), 3600, msg=f'{view_name} should be cacheable')
            with override_lang('cy'):
                response = self.client.get(reverse(view_name))
                self.assertGreaterEqual(get_max_age(response), 3600, msg=f'{view_name} should be cacheable')

    def test_feedback_views_are_uncacheable(self):
        view_names = [
            'submit_ticket', 'feedback_success',
            'healthcheck_json', 'ping_json',
        ]
        with responses.RequestsMock() as rsps:
            rsps.add(rsps.GET, '%s/%s' % (settings.API_URL, 'healthcheck.json'), json={})
            for view_name in view_names:
                response = self.client.get(reverse(view_name))
                self.assertResponseNotCacheable(response)
