from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _


def support_links(request):
    return {
        'support_links': [
            {
                'url': reverse('send_money:privacy_policy'),
                'title': _('Privacy Policy'),
            },
            {
                'url': reverse('send_money:cookies'),
                'title': _('Cookies'),
            },
            {
                'url': reverse('submit_ticket'),
                'title': _('Feedback'),
            },
        ]
    }
