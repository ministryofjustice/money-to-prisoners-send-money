from django.conf import settings
from django.conf.urls import include, url
from django.core.urlresolvers import reverse_lazy
from django.views.generic import TemplateView
from django.views.generic.base import RedirectView

from moj_irat.views import HealthcheckView, PingJsonView

urlpatterns = [
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

    url(r'^ping.json$', PingJsonView.as_view(
        build_date_key='APP_BUILD_DATE',
        commit_id_key='APP_GIT_COMMIT',
        version_number_key='APP_BUILD_TAG',
    ), name='ping_json'),
    url(r'^healthcheck.json$', HealthcheckView.as_view(), name='healthcheck_json'),
]

if not settings.HIDE_PAYMENT_PAGES:
    urlpatterns.append(url(r'^', include('send_money.urls', namespace='send_money',)))
else:
    urlpatterns.append(url(r'^$', RedirectView.as_view(url=reverse_lazy('submit_ticket'))))
