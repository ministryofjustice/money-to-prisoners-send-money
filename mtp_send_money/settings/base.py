"""
Django settings for mtp_send_money project.

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.9/ref/settings/
"""
from decimal import Decimal
from functools import partial
import os
from os.path import abspath, dirname, join
import sys

BASE_DIR = dirname(dirname(abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))

get_project_dir = partial(join, BASE_DIR)

APP = 'send-money'
ENVIRONMENT = os.environ.get('ENV', 'local')


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
SECRET_KEY = 'CHANGE_ME'
ALLOWED_HOSTS = []

SITE_URL = os.environ.get('SITE_URL', 'http://localhost:8004')

# Application definition
INSTALLED_APPS = (
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.contenttypes',
    'django.contrib.auth',
)
PROJECT_APPS = (
    'mtp_utils',
    'send_money',
    'zendesk_tickets'
)
INSTALLED_APPS += PROJECT_APPS


WSGI_APPLICATION = 'mtp_send_money.wsgi.application'
ROOT_URLCONF = 'mtp_send_money.urls'
MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'moj_auth.csrf.CsrfViewMiddleware',
    'send_money.middleware.SendMoneyAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
)

HEALTHCHECKS = []
AUTODISCOVER_HEALTHCHECKS = True

# security tightening
# some overridden in prod/docker settings where SSL is ensured
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = False
CSRF_FAILURE_VIEW = 'moj_auth.csrf.csrf_failure'


# Database
DATABASES = {}


# Internationalization
LANGUAGE_CODE = 'en-gb'
TIME_ZONE = 'Europe/London'
USE_I18N = True
USE_L10N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_ROOT = 'static'
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    get_project_dir('assets'),
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            get_project_dir('templates'),
            get_project_dir('node_modules'),
            get_project_dir('../node_modules/mojular-templates'),
            get_project_dir('../node_modules/money-to-prisoners-common/templates')
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'mtp_utils.context_processors.analytics',
                'mtp_utils.context_processors.app_environment',
                'send_money.context_processors.support_links'
            ],
        },
    },
]

# logging settings
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '%(asctime)s [%(levelname)s] %(message)s',
            'datefmt': '%Y-%m-%dT%H:%M:%S',
        },
        'elk': {
            '()': 'mtp_utils.logging.ELKFormatter'
        },
    },
    'handlers': {
        'null': {
            'level': 'DEBUG',
            'class': 'logging.NullHandler',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple' if ENVIRONMENT == 'local' else 'elk',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'root': {
        'level': 'WARNING',
        'handlers': ['console'],
    },
    'loggers': {
        'django.security.DisallowedHost': {
            'handlers': ['null'],
            'propagate': False,
        },
        'mtp': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
    },
}

# sentry exception handling
if os.environ.get('SENTRY_DSN'):
    INSTALLED_APPS = ('raven.contrib.django.raven_compat',) + INSTALLED_APPS
    RAVEN_CONFIG = {
        'dsn': os.environ['SENTRY_DSN'],
        'release': os.environ.get('APP_GIT_COMMIT', 'unknown'),
    }
    LOGGING['handlers']['sentry'] = {
        'level': 'ERROR',
        'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler'
    }
    LOGGING['root']['handlers'].append('sentry')
    LOGGING['loggers']['mtp']['handlers'].append('sentry')

TEST_RUNNER = 'mtp_utils.test_utils.runner.TestRunner'

# authentication
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

AUTHENTICATION_BACKENDS = (
    'moj_auth.backends.MojBackend',
)


def find_api_url():
    import socket
    import subprocess

    api_port = int(os.environ.get('API_PORT', '8000'))
    try:
        host_machine_ip = subprocess.check_output(['docker-machine', 'ip', 'default'],
                                                  stderr=subprocess.DEVNULL)
        host_machine_ip = host_machine_ip.decode('ascii').strip()
        with socket.socket() as sock:
            sock.connect((host_machine_ip, api_port))
    except (subprocess.CalledProcessError, OSError):
        host_machine_ip = 'localhost'
    return 'http://%s:%s' % (host_machine_ip, api_port)


API_CLIENT_ID = 'send-money'
API_CLIENT_SECRET = os.environ.get('API_CLIENT_SECRET', 'send-money')
API_URL = os.environ.get('API_URL', find_api_url())

SHARED_API_USERNAME = os.environ.get('SHARED_API_USERNAME', 'send-money')
SHARED_API_PASSWORD = os.environ.get('SHARED_API_PASSWORD', 'send-money')

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'send_money:start'
LOGOUT_URL = 'logout'

OAUTHLIB_INSECURE_TRANSPORT = True

NOMS_HOLDING_ACCOUNT_NUMBER = os.environ.get('NOMS_HOLDING_ACCOUNT_NUMBER', '########')
NOMS_HOLDING_ACCOUNT_SORT_CODE = os.environ.get('NOMS_HOLDING_ACCOUNT_SORT_CODE', '##-##-##')

SERVICE_CHARGE_PERCENTAGE = Decimal('2.4')  # always use `Decimal` percentage
SERVICE_CHARGE_FIXED = Decimal('0.20')  # always use `Decimal` in pounds
SERVICE_CHARGED = SERVICE_CHARGE_PERCENTAGE > Decimal('0') or \
                  SERVICE_CHARGE_FIXED > Decimal('0')

GOOGLE_ANALYTICS_ID = os.environ.get('GOOGLE_ANALYTICS_ID', None)

REQUEST_PAGE_SIZE = 500

ZENDESK_BASE_URL = 'https://ministryofjustice.zendesk.com'
ZENDESK_API_USERNAME = os.environ.get('ZENDESK_API_USERNAME', '')
ZENDESK_API_TOKEN = os.environ.get('ZENDESK_API_TOKEN', '')
ZENDESK_REQUESTER_ID = os.environ.get('ZENDESK_REQUESTER_ID', '')
ZENDESK_GROUP_ID = 26417927
ZENDESK_CUSTOM_FIELDS = {
    'referer': 26047167,
    'username': 29241738,
    'user_agent': 23791776,
    'contact_email': 30769508
}

CITIZEN_INFO_URL = 'sendmoneytoaprisoner.service.justice.gov.uk'

SHOW_BANK_TRANSFER_OPTION = os.environ.get('SHOW_BANK_TRANSFER_OPTION', 'True') == 'True'
SHOW_DEBIT_CARD_OPTION = os.environ.get('SHOW_DEBIT_CARD_OPTION', 'True') == 'True'

GOVUK_PAY_URL = os.environ.get('GOVUK_PAY_URL', '')
GOVUK_PAY_AUTH_TOKEN = os.environ.get('GOVUK_PAY_AUTH_TOKEN', '')


try:
    from .local import *  # noqa
except ImportError:
    pass
