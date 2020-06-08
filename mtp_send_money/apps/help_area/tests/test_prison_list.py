from django.urls import reverse
import responses

from send_money.tests import BaseTestCase, mock_auth
from send_money.utils import api_url


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
            response = self.client.get(reverse('prison_list'))
            self.assertIn('exclude_empty_prisons=True', rsps.calls[-1].request.url)
        self.assertContains(response, 'Prison 1')
        response = response.content.decode(response.charset)
        self.assertIn('Prison 2', response)
        self.assertLess(response.index('Prison 1'), response.index('Prison 2'))
