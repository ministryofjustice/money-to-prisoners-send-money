from django.conf import settings
from django.conf.urls import url
from django.urls import reverse_lazy
from django.views.generic import RedirectView

from help_area import views
from send_money.utils import CacheableTemplateView

app_name = 'help_area'
urlpatterns = [
    url(r'^help/$',
        views.HelpView.as_view(
            template_name='help_area/help.html',
            back_url=settings.START_PAGE_URL,
        ),
        name='help'),
    url(r'^help/with-making-a-payment/$',
        views.HelpView.as_view(
            template_name='help_area/help-new-payment.html',
            back_url=reverse_lazy('help_area:help'),
        ),
        name='help-new-payment'),
    url(r'^help/with-a-payment-i-sent/$',
        views.HelpView.as_view(
            template_name='help_area/help-sent-payment.html',
            back_url=reverse_lazy('help_area:help'),
        ),
        name='help-sent-payment'),

    url(r'^help/bank-transfer-issues/$',
        RedirectView.as_view(url=reverse_lazy('help_area:help-sent-payment'), permanent=True)),
    url(r'^help/payment-delay/$',
        RedirectView.as_view(url=reverse_lazy('help_area:help-sent-payment'), permanent=True)),
    url(r'^help/prisoner-moved-or-released/$',
        RedirectView.as_view(url=reverse_lazy('help_area:help-sent-payment'), permanent=True)),

    url(r'^help/prisons/$', views.PrisonListView.as_view(), name='prison_list'),

    url(r'^help/faq/$', CacheableTemplateView.as_view(template_name='help_area/faq.html'), name='faq'),

    url(r'^contact-us/$', views.GetHelpView.as_view(), name='submit_ticket'),
    url(r'^contact-us/success/$', views.GetHelpSuccessView.as_view(), name='feedback_success'),
]
