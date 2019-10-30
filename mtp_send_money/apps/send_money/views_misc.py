import logging

from django import forms
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import is_safe_url
from django.utils.translation import gettext_lazy as _, override as override_language
from django.views.generic import FormView, TemplateView
from mtp_common.analytics import AnalyticsPolicy
from mtp_common.api import retrieve_all_pages_for_path
from oauthlib.oauth2 import OAuth2Error
from requests import RequestException

from send_money.utils import get_api_session, make_response_cacheable

logger = logging.getLogger('mtp')


def help_view(request, page='payment-issues'):
    """
    FAQ sections
    @param request: the HTTP request
    @param page: page slug
    """
    context = {
        'breadcrumbs_back': settings.START_PAGE_URL,
    }
    return_to = request.META.get('HTTP_REFERER') or ''
    return_to_within_site = is_safe_url(url=return_to, host=request.get_host())
    return_to_same_page = return_to.split('?')[0] == request.build_absolute_uri().split('?')[0]
    if page != 'payment-issues' and return_to_within_site and not return_to_same_page:
        context['breadcrumbs_back'] = return_to
    response = render(request, 'send_money/help/%s.html' % page, context=context)
    return make_response_cacheable(response)


def prison_list_view(request):
    """
    List the prisons that MTP supports
    """
    prison_list = cache.get('prison_list')
    if not prison_list:
        try:
            session = get_api_session()
            prison_list = retrieve_all_pages_for_path(session, '/prisons/', exclude_empty_prisons=True)
            prison_list = [
                prison['name']
                for prison in sorted(prison_list, key=lambda prison: prison['short_name'])
            ]
            if not prison_list:
                raise ValueError('Empty prison list')
            cache.set('prison_list', prison_list, timeout=60 * 60)
        except (RequestException, OAuth2Error, ValueError):
            logger.exception('Could not look up prison list')
    response = render(request, 'send_money/prison-list.html', context={
        'breadcrumbs_back': reverse('send_money:help'),
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
    return make_response_cacheable(response)


class CookiesForm(forms.Form):
    accept_cookies = forms.ChoiceField(label=_('Accept cookies to improve the service'), choices=(
        ('yes', _('Yes')),
        ('no', _('No')),
    ))
    next = forms.CharField(label=_('Page to show next'), required=False)


class CookiesView(FormView):
    form_class = CookiesForm
    template_name = 'cookies.html'
    success_url = reverse_lazy('cookies')

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data['cookie_policy_cookie_name'] = AnalyticsPolicy.cookie_name
        return context_data

    def get_initial(self):
        initial = super().get_initial()
        cookie_policy_accepted = AnalyticsPolicy(self.request).is_cookie_policy_accepted(self.request)
        initial['accept_cookies'] = 'yes' if cookie_policy_accepted else 'no'
        return initial

    def form_valid(self, form):
        success_url = form.cleaned_data['next']
        if success_url and is_safe_url(success_url, host=self.request.get_host()):
            response = redirect(success_url)
        else:
            response = super().form_valid(form)
        cookie_policy_accepted = form.cleaned_data['accept_cookies'] == 'yes'
        AnalyticsPolicy(self.request).set_cookie_policy(response, cookie_policy_accepted)
        return response


def robots_txt_view(request):
    """
    robots.txt - blocks access on non-prod and refers to sitemap.xml
    @param request: the HTTP request
    """
    if settings.ENVIRONMENT != 'prod':
        robots_txt = 'User-agent: *\nDisallow: /'
    else:
        robots_txt = 'Sitemap: %s' % request.build_absolute_uri(reverse('sitemap_xml'))
    response = HttpResponse(robots_txt, content_type='text/plain')
    return make_response_cacheable(response)


class SitemapXMLView(TemplateView):
    """
    sitemap.xml - links search engines to the main content pages
    """
    template_name = 'send_money/sitemap.xml'
    content_type = 'application/xml; charset=utf-8'

    def make_links(self):
        url_names = [
            'send_money:choose_method',
            'send_money:help', 'send_money:faq',
            'send_money:help_bank_transfer', 'send_money:help_delays', 'send_money:help_transfered',
            'send_money:prison_list',
            'terms', 'privacy', 'cookies',
        ]
        links = {}
        request = self.request
        for lang_code, _lang_name in settings.LANGUAGES:
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

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        return make_response_cacheable(response)
