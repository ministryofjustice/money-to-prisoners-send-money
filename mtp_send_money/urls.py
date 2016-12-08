from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.i18n import i18n_patterns
from django.template.response import TemplateResponse
from django.views.generic import TemplateView
from django.views.generic.base import RedirectView
from moj_irat.views import HealthcheckView, PingJsonView

from send_money.views_misc import SitemapXMLView, robots_txt_view

urlpatterns = i18n_patterns(
    url(r'^', include('send_money.urls', namespace='send_money',)),

    url(r'^', include('feedback.urls')),

    url(
        r'^terms/$',
        TemplateView.as_view(template_name='terms.html'),
        name='terms',
    ),
    url(
        r'^cookies/$',
        TemplateView.as_view(template_name='cookies.html'),
        name='cookies',
    ),
)

urlpatterns += [
    url(r'^ping.json$', PingJsonView.as_view(
        build_date_key='APP_BUILD_DATE',
        commit_id_key='APP_GIT_COMMIT',
        version_number_key='APP_BUILD_TAG',
    ), name='ping_json'),
    url(r'^healthcheck.json$', HealthcheckView.as_view(), name='healthcheck_json'),

    url(r'^robots.txt$', robots_txt_view),
    url(r'^sitemap.xml$', SitemapXMLView.as_view(), name='sitemap_xml'),

    url(r'^favicon.ico$', RedirectView.as_view(url=settings.STATIC_URL + 'images/favicon.ico', permanent=True)),

    url(r'^404.html$', lambda request: TemplateResponse(request, 'mtp_common/errors/404.html', status=404)),
    url(r'^500.html$', lambda request: TemplateResponse(request, 'mtp_common/errors/500.html', status=500)),
]

handler404 = 'mtp_common.views.page_not_found'
handler500 = 'mtp_common.views.server_error'
handler400 = 'mtp_common.views.bad_request'
