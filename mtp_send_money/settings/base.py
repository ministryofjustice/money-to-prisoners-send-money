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
APP_BUILD_DATE = os.environ.get('APP_BUILD_DATE')
APP_GIT_COMMIT = os.environ.get('APP_GIT_COMMIT')
MOJ_INTERNAL_SITE = False

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
SECRET_KEY = 'CHANGE_ME'
ALLOWED_HOSTS = []

START_PAGE_URL = os.environ.get('START_PAGE_URL', 'https://www.gov.uk/send-prisoner-money')
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
    'anymail',
    'mtp_common',
    'send_money',
    'zendesk_tickets'
)
INSTALLED_APPS += PROJECT_APPS


WSGI_APPLICATION = 'mtp_send_money.wsgi.application'
ROOT_URLCONF = 'mtp_send_money.urls'
MIDDLEWARE = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'mtp_common.auth.csrf.CsrfViewMiddleware',
    'send_money.middleware.SendMoneyMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'mtp_common.analytics.ReferrerPolicyMiddleware',
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
CSRF_FAILURE_VIEW = 'mtp_common.auth.csrf.csrf_failure'


# Database
DATABASES = {}


# Internationalization
LANGUAGE_CODE = 'en-gb'
LANGUAGES = (
    ('en-gb', 'English'),
    ('cy', 'Cymraeg'),
)
LOCALE_PATHS = (get_project_dir('translations'),)
TIME_ZONE = 'Europe/London'
USE_I18N = True
USE_L10N = True
USE_TZ = True
FORMAT_MODULE_PATH = ['mtp_send_money.settings.formats']


# Static files (CSS, JavaScript, Images)
STATIC_ROOT = 'static'
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    get_project_dir('assets'),
    get_project_dir('assets-static'),
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            get_project_dir('templates'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'mtp_common.context_processors.analytics',
                'mtp_common.context_processors.app_environment',
                'mtp_common.context_processors.govuk_localisation',
                'send_money.context_processors.links',
                'mtp_common.analytics.default_genericised_pageview',
            ],
        },
    },
]

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'mtp',
    }
}

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
            '()': 'mtp_common.logging.ELKFormatter'
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
        'release': APP_GIT_COMMIT or 'unknown',
    }
    LOGGING['handlers']['sentry'] = {
        'level': 'ERROR',
        'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler'
    }
    LOGGING['root']['handlers'].append('sentry')
    LOGGING['loggers']['mtp']['handlers'].append('sentry')

TEST_RUNNER = 'mtp_common.test_utils.runner.TestRunner'

# authentication
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

AUTHENTICATION_BACKENDS = (
    'mtp_common.auth.backends.MojBackend',
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

OAUTHLIB_INSECURE_TRANSPORT = True

NOMS_HOLDING_ACCOUNT_NUMBER = os.environ.get('NOMS_HOLDING_ACCOUNT_NUMBER', '########')
NOMS_HOLDING_ACCOUNT_SORT_CODE = os.environ.get('NOMS_HOLDING_ACCOUNT_SORT_CODE', '##-##-##')

ENABLE_PAYMENT_CHOICE_EXPERIMENT = os.environ.get('ENABLE_PAYMENT_CHOICE_EXPERIMENT', 'True') == 'True'

SERVICE_CHARGE_PERCENTAGE = Decimal(
    os.environ.get('SERVICE_CHARGE_PERCENTAGE', '0')
)  # always use `Decimal` percentage
SERVICE_CHARGE_FIXED = Decimal(
    os.environ.get('SERVICE_CHARGE_FIXED', '0')
)  # always use `Decimal` in pounds

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

SHOW_BANK_TRANSFER_OPTION = os.environ.get('SHOW_BANK_TRANSFER_OPTION', 'True') == 'True'
SHOW_DEBIT_CARD_OPTION = os.environ.get('SHOW_DEBIT_CARD_OPTION', 'True') == 'True'
BANK_TRANSFER_PRISONS = os.environ.get('BANK_TRANSFER_PRISONS', '')
DEBIT_CARD_PRISONS = os.environ.get('DEBIT_CARD_PRISONS', '')
SHOW_LANGUAGE_SWITCH = os.environ.get('SHOW_LANGUAGE_SWITCH', 'False') == 'True'
CONFIRMATION_EXPIRES = 60  # minutes

GOVUK_PAY_URL = os.environ.get('GOVUK_PAY_URL', '')
GOVUK_PAY_AUTH_TOKEN = os.environ.get('GOVUK_PAY_AUTH_TOKEN', '')
GOVUK_PAY_CONNECTION_CHECK_IMAGE = os.environ.get(
    'GOVUK_PAY_CONNECTION_CHECK_IMAGE',
    'https://www.payments.service.gov.uk/assets/images/govuk-crest.png',
)

EMAIL_BACKEND = 'anymail.backends.mailgun.EmailBackend'
ANYMAIL = {
    'MAILGUN_API_KEY': os.environ.get('MAILGUN_ACCESS_KEY', ''),
    'MAILGUN_SENDER_DOMAIN': os.environ.get('MAILGUN_SERVER_NAME', ''),
    'SEND_DEFAULTS': {
        'tags': [APP, ENVIRONMENT],
    },
}
MAILGUN_FROM_ADDRESS = os.environ.get('MAILGUN_FROM_ADDRESS', '')
if MAILGUN_FROM_ADDRESS:
    DEFAULT_FROM_EMAIL = MAILGUN_FROM_ADDRESS

try:
    from .local import *  # noqa
except ImportError:
    pass
