from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _


def support_links(request):
    return {
        'support_links': [
            {
                'url': reverse('privacy_policy'),
                'title': _('Privacy Policy'),
            },
            {
                'url': reverse('cookies'),
                'title': _('Cookies'),
            },
            {
                'url': reverse('submit_ticket'),
                'title': _('Feedback'),
            },
        ]
    }
