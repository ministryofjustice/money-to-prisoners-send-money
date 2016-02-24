from django.conf import settings
from django.conf.urls import include, url
from django.views.generic import TemplateView

from moj_irat.views import HealthcheckView, PingJsonView

urlpatterns = [
    url(r'^', include('feedback.urls')),

    url(
        r'^privacy-policy/$',
        TemplateView.as_view(template_name='privacy-policy.html'),
        name='privacy_policy',
    ),
    url(
        r'^cookies/$',
        TemplateView.as_view(template_name='cookies.html'),
        name='cookies',
    ),

    url(r'^ping.json$', PingJsonView.as_view(
        build_date_key='APP_BUILD_DATE',
        commit_id_key='APP_GIT_COMMIT',
        version_number_key='APP_BUILD_TAG',
    ), name='ping_json'),
    url(r'^healthcheck.json$', HealthcheckView.as_view(), name='healthcheck_json'),
]

if not settings.HIDE_PAYMENT_PAGES:
    urlpatterns.append(url(r'^', include('send_money.urls', namespace='send_money',)))
