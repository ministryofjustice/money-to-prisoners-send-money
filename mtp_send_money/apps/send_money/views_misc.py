import logging

from django.conf import settings
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.http import is_safe_url
from django.utils.translation import override as override_language
from django.views.generic import TemplateView
from mtp_common.api import retrieve_all_pages
from oauthlib.oauth2 import OAuth2Error
from requests import RequestException
from slumber.exceptions import SlumberHttpBaseException

from send_money.utils import get_api_client

logger = logging.getLogger('mtp')


def help_view(request, page='payment-issues'):
    """
    FAQ sections
    @param request: the HTTP request
    @param page: page slug
    """
    context = {
        'return_to': reverse('send_money:choose_method'),
    }
    return_to = request.META.get('HTTP_REFERER')
    if is_safe_url(url=return_to, host=request.get_host()) and return_to != request.build_absolute_uri():
        context['return_to'] = return_to
    return render(request, 'send_money/help/%s.html' % page, context=context)


def prison_list_view(request):
    """
    List the prisons that MTP supports
    """
    prison_list = cache.get('prison_list')
    if not prison_list:
        try:
            client = get_api_client()
            prison_list = retrieve_all_pages(client.prisons.get, exclude_empty_prisons=True)
            prison_list = [
                prison['name']
                for prison in sorted(prison_list, key=lambda prison: prison['short_name'])
            ]
            if not prison_list:
                raise ValueError('Empty prison list')
            cache.set('prison_list', prison_list, timeout=60 * 60)
        except (SlumberHttpBaseException, RequestException, OAuth2Error, ValueError):
            logger.exception('Could not look up prison list')
    return render(request, 'send_money/prison-list.html', context={
        'prison_list': prison_list,
        'stop_words': sorted([
            # NB: these are output into a regular expression so must have special characters escaped
            'and', 'the',
            'prison', 'prisons',
            'young', 'offender', 'institutions', 'institutions',
            'immigration', 'removal', 'centre', 'centres',
            'secure', 'training',
        ]),
    })


def robots_txt_view(request):
    """
    robots.txt - blocks access on non-prod and refers to sitemap.xml
    @param request: the HTTP request
    """
    if settings.ENVIRONMENT != 'prod':
        robots_txt = 'User-agent: *\nDisallow: /'
    else:
        robots_txt = 'Sitemap: %s' % request.build_absolute_uri(reverse('sitemap_xml'))
    return HttpResponse(robots_txt, content_type='text/plain')


class SitemapXMLView(TemplateView):
    """
    sitemap.xml - links search engines to the main content pages
    """
    template_name = 'send_money/sitemap.xml'
    content_type = 'application/xml; charset=utf-8'

    def make_links(self):
        url_names = ['send_money:choose_method', 'send_money:help', 'send_money:prison_list']
        links = {}
        request = self.request
        for lang_code, lang_name in settings.LANGUAGES:
            with override_language(lang_code):
                links[lang_code] = {
                    url_name: request.build_absolute_uri(reverse(url_name))
                    for url_name in url_names
                }
        return (
            {
                'url': links[settings.LANGUAGE_CODE][url_name],
                'alt_links': (
                    {
                        'lang': lang_code,
                        'url': links[lang_code][url_name],
                    }
                    for lang_code, lang_name in settings.LANGUAGES
                ) if settings.SHOW_LANGUAGE_SWITCH else []
            }
            for url_name in url_names
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(links=self.make_links(), **kwargs)
