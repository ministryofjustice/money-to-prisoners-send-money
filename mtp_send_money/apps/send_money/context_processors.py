from django.core.urlresolvers import reverse
from django.utils.translation import gettext


def support_links(_):
    return {
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
        ]
    }
