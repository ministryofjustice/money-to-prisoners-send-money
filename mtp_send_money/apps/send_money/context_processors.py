from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _


def support_links(request):
    return {
        'support_links': [
            {
                'url': reverse('terms'),
                'title': _('Terms and conditions'),
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
