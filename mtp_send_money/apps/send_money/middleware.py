import logging

from django.http import Http404
from django.utils.translation import ugettext as _

from moj_auth import logout
from moj_auth.exceptions import Unauthorized
from moj_auth.middleware import AuthenticationMiddleware

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
