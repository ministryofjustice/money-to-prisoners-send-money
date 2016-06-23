import logging

from django.http import Http404
from django.utils.translation import ugettext as _

from mtp_common.auth.exceptions import Unauthorized
from mtp_common.auth.models import MojAnonymousUser

logger = logging.getLogger('mtp')


class SendMoneyAuthenticationMiddleware:
    def process_request(self, request):
        request.user = MojAnonymousUser()

    def process_exception(self, request, exception):
        if isinstance(exception, Unauthorized):
            logger.error(
                'Shared send money user was not authorised to access api'
            )
            raise Http404(_('Could not connect to service, please try again later'))
