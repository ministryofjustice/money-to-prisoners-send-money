"""
Docker settings
"""
from mtp_common.stack import get_current_pod

from .base import *  # noqa
from .base import ENVIRONMENT, os

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG') == 'True'

ALLOWED_HOSTS = [
    'localhost',
    '.service.gov.uk',
    '.service.justice.gov.uk',
    '.svc.cluster.local',
]

current_pod = get_current_pod()
if current_pod and current_pod.status.pod_ip:
    ALLOWED_HOSTS.append(current_pod.status.pod_ip)

OAUTHLIB_INSECURE_TRANSPORT = os.environ.get('OAUTHLIB_INSECURE_TRANSPORT') == 'True'
if not OAUTHLIB_INSECURE_TRANSPORT:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = ''

# security tightening
if ENVIRONMENT != 'local':
    # ssl redirect done at nginx and kubernetes level
    # SECURE_SSL_REDIRECT = True
    # strict-transport set at nginx level
    # SECURE_HSTS_SECONDS = 31536000
    # SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_BROWSER_XSS_FILTER = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
