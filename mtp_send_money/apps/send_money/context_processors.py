from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext
from mtp_common.analytics import AnalyticsPolicy


def analytics(request):
    return {
        'actioned_cookie_prompt': AnalyticsPolicy.cookie_name in request.COOKIES,
    }


def links(_):
    return {
        'service_name': gettext('Send money to someone in prison'),
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
                'url': reverse('help_area:help'),
                'title': gettext('Help'),
            },
        ],
    }
