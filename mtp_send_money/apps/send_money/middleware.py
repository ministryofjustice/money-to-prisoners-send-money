import logging

from django.http import Http404
from django.utils.translation import ugettext as _

from mtp_common.auth import logout
from mtp_common.auth.exceptions import Unauthorized
from mtp_common.auth.middleware import AuthenticationMiddleware

logger = logging.getLogger('mtp')


class SendMoneyAuthenticationMiddleware(AuthenticationMiddleware):
    def process_exception(self, request, exception):
        if isinstance(exception, Unauthorized):
            logger.error(
                'Shared send money user was not authorised to access api'
            )
            logout(request)
            raise Http404(_('Could not connect to service, '
                            'please try again later'))
