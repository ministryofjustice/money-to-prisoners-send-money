import csv
import json
import warnings

from django import forms
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.cache import patch_cache_control
from django.utils.dateparse import parse_date
from django.utils.http import is_safe_url
from django.utils.translation import gettext_lazy as _, override as override_language
from django.views.generic import FormView, RedirectView, TemplateView, View
from mtp_common.analytics import AnalyticsPolicy

from send_money.utils import api_url, get_api_session, make_response_cacheable


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
        if success_url and is_safe_url(success_url, allowed_hosts={self.request.get_host()}):
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


class InvalidDateException(Exception):
    pass


class PerformanceDataCsvView(View):
    """
    Gets Performance Data from API and send it as CSV file.

    Result shouldn't change for a week hence the caching.

    @param request: the HTTP request
    """

    def get(self, request):
        errors = []

        try:
            date_from = self.parse_date(request.GET.get('from'))
        except InvalidDateException as e:
            errors.append(str(e))

        try:
            date_to = self.parse_date(request.GET.get('to'))
        except InvalidDateException as e:
            errors.append(str(e))

        if errors:
            response_body = json.dumps({'errors': errors})
            return HttpResponse(response_body, status=400, content_type='application/json')

        api_client = get_api_session()
        api_params = {'week__gte': date_from, 'week__lt': date_to}
        data = api_client.get(api_url('performance/data'), params=api_params)
        data = data.json()

        response = HttpResponse(content_type='text/csv')

        writer = csv.DictWriter(response, fieldnames=data['headers'].keys())
        writer.writerow(data['headers'])
        writer.writerows(data['results'])

        # Public and cachable for a week
        patch_cache_control(response, public=True, max_age=604800)

        return response

    def parse_date(self, date_input):
        if not date_input:
            return None

        date = parse_date(date_input)
        if not date:
            error = _('Date "%s" could not be parsed - use YYYY-MM-DD format') % date_input
            raise InvalidDateException(error)

        return date


class SitemapXMLView(TemplateView):
    """
    sitemap.xml - links search engines to the main content pages
    """
    template_name = 'send_money/sitemap.xml'
    content_type = 'application/xml; charset=utf-8'

    def make_links(self):
        url_names = [
            'send_money:user_agreement',
            'send_money:choose_method',
            'help_area:help', 'help_area:help-new-payment', 'help_area:help-sent-payment',
            'help_area:help-cannot-access',
            'help_area:help-setup-basic-bank-account', 'help_area:help-apply-for-exemption',
            'help_area:prison_list',
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
                'alt_links': [
                    {
                        'lang': lang_code,
                        'url': links[lang_code][url_name],
                    }
                    for lang_code, lang_name in settings.LANGUAGES
                ] if settings.SHOW_LANGUAGE_SWITCH else []
            }
            for url_name in url_names
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(links=self.make_links(), **kwargs)

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        return make_response_cacheable(response)


class LegacyFeedbackView(RedirectView):
    url = reverse_lazy('help_area:help')
    permanent = True

    def dispatch(self, request, *args, **kwargs):
        warnings.warn('`submit_ticket` view has been renamed')
        return super().dispatch(request, *args, **kwargs)
