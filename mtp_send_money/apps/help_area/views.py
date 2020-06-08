import logging

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.http import is_safe_url
from django.utils.translation import gettext_lazy as _
from mtp_common.api import retrieve_all_pages_for_path
from mtp_common.views import GetHelpView as BaseGetHelpView, GetHelpSuccessView as BaseGetHelpSuccessView
from oauthlib.oauth2 import OAuth2Error
from requests import RequestException

from help_area.forms import ContactForm
from send_money.utils import CacheableTemplateView, get_api_session, make_response_cacheable

logger = logging.getLogger('mtp')


class GetHelpView(BaseGetHelpView):
    form_class = ContactForm
    success_url = reverse_lazy('help_area:feedback_success')
    template_name = 'send_money/contact-form.html'
    ticket_subject = 'MTP for Family Services - Send money to someone in prison'
    ticket_tags = ['feedback', 'mtp', 'send-money', settings.ENVIRONMENT]
    ticket_template_name = 'send_money/contact-form-ticket.txt'

    def get_context_data(self, **kwargs):
        kwargs['get_help_title'] = _('Contact us')
        return super().get_context_data(**kwargs)


class GetHelpSuccessView(BaseGetHelpSuccessView):
    template_name = 'send_money/contact-form-success.html'

    def get_context_data(self, **kwargs):
        kwargs['get_help_title'] = _('Contact us')
        return super().get_context_data(**kwargs)


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
    response = render(request, 'help_area/%s.html' % page, context=context)
    return make_response_cacheable(response)


class PrisonListView(CacheableTemplateView):
    """
    List the prisons that MTP supports
    """
    template_name = 'help_area/prison-list.html'

    @classmethod
    def get_prison_list(cls):
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
        return prison_list

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data.update({
            'breadcrumbs_back': reverse('help_area:help'),
            'prison_list': self.get_prison_list(),
            'stop_words': sorted([
                # NB: these are output into a regular expression so must have special characters escaped
                'and', 'the',
                'prison', 'prisons',
                'young', 'offender', 'institutions', 'institutions',
                'immigration', 'removal', 'centre', 'centres',
                'secure', 'training',
            ]),
        })
        return context_data
