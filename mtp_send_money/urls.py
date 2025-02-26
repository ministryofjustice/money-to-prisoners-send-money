from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.template.response import TemplateResponse
from django.urls import include, re_path
from django.views.decorators.cache import cache_control
from django.views.generic.base import RedirectView
from django.views.i18n import JavaScriptCatalog
from moj_irat.views import HealthcheckView, PingJsonView
from mtp_common.metrics.views import metrics_view

from send_money.utils import CacheableTemplateView
from send_money.views_misc import (
    CookiesView,
    LegacyFeedbackView,
    SitemapXMLView,
    PerformanceDataCsvView,
    robots_txt_view,
)


urlpatterns = i18n_patterns(
    re_path(r'^', include('send_money.urls', namespace='send_money')),

    re_path(r'^', include('help_area.urls', namespace='help_area')),
    # this is needed to warn about references to the legacy url path and name:
    re_path(r'^feedback/$', LegacyFeedbackView.as_view(), name='submit_ticket'),

    re_path(r'^terms/$', CacheableTemplateView.as_view(template_name='terms.html'), name='terms'),
    re_path(r'^privacy/$', CacheableTemplateView.as_view(template_name='privacy.html'), name='privacy'),
    re_path(r'^cookies/$', CookiesView.as_view(), name='cookies'),
    re_path(r'^accessibility/$', CacheableTemplateView.as_view(template_name='accessibility.html'), name='accessibility'),

    re_path(r'^js-i18n.js$', cache_control(public=True, max_age=86400)(JavaScriptCatalog.as_view()), name='js-i18n'),

    re_path(r'^404.html$', lambda request: TemplateResponse(request, 'mtp_common/errors/404.html', status=404)),
    re_path(r'^500.html$', lambda request: TemplateResponse(request, 'mtp_common/errors/500.html', status=500)),
)

urlpatterns += [
    re_path(r'^ping.json$', PingJsonView.as_view(
        build_date_key='APP_BUILD_DATE',
        commit_id_key='APP_GIT_COMMIT',
        version_number_key='APP_BUILD_TAG',
    ), name='ping_json'),
    re_path(r'^healthcheck.json$', HealthcheckView.as_view(), name='healthcheck_json'),
    re_path(r'^metrics.txt$', metrics_view, name='prometheus_metrics'),

    re_path(r'^robots.txt$', robots_txt_view),
    re_path(r'^performance-data.csv$', PerformanceDataCsvView.as_view(), name='performance_data_csv'),
    re_path(r'^sitemap.xml$', SitemapXMLView.as_view(), name='sitemap_xml'),

    re_path(r'^\.well-known/security\.txt$', RedirectView.as_view(
        url='https://security-guidance.service.justice.gov.uk/.well-known/security.txt',
        permanent=True,
    )),

    re_path(r'^favicon.ico$', RedirectView.as_view(url=settings.STATIC_URL + 'images/favicon.ico', permanent=True)),
]

handler404 = 'mtp_common.views.page_not_found'
handler500 = 'mtp_common.views.server_error'
handler400 = 'mtp_common.views.bad_request'
