import logging

from django.http import Http404
from django.utils.cache import add_never_cache_headers
from django.utils.translation import gettext as _

from mtp_common.auth.exceptions import Unauthorized
from mtp_common.auth.models import MojAnonymousUser

logger = logging.getLogger('mtp')


class SendMoneyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = MojAnonymousUser()
        response = self.get_response(request)
        if not response.has_header('Cache-Control'):
            add_never_cache_headers(response)
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, Unauthorized):
            logger.error(
                'Shared send money user was not authorised to access api'
            )
            raise Http404(_('Could not connect to service, please try again later'))
