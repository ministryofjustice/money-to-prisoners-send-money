from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext


def actioned_cookie_prompt(request):
    return {
        'actioned_cookie_prompt': 'cookie_policy' in request.COOKIES,
    }


def links(_):
    return {
        'site_url': settings.START_PAGE_URL,
        'support_links': [
            {
                'url': reverse('terms'),
                'title': gettext('Terms and conditions'),
            },
            {
                'url': reverse('cookies'),
                'title': gettext('Cookies'),
            },
            {
                'url': reverse('submit_ticket'),
                'title': gettext('Feedback'),
            },
        ],
    }
