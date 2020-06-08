from django.conf.urls import url
from django.views.generic import TemplateView

from help_area import views

app_name = 'help_area'
urlpatterns = [
    url(r'^help/$', views.help_view, name='help'),
    url(r'^help/bank-transfer-issues/$', views.help_view, kwargs={'page': 'bank-transfer-issues'},
        name='help_bank_transfer'),
    url(r'^help/payment-delay/$', views.help_view, kwargs={'page': 'payment-delay'},
        name='help_delays'),
    url(r'^help/prisoner-moved-or-released/$', views.help_view, kwargs={'page': 'prisoner-moved-or-released'},
        name='help_transfered'),
    url(r'^help/prisons/$', views.prison_list_view, name='prison_list'),

    url(r'^help/faq/$', TemplateView.as_view(template_name='help_area/faq.html'), name='faq'),

    url(r'^contact-us/$', views.GetHelpView.as_view(), name='submit_ticket'),
    url(r'^contact-us/success/$', views.GetHelpSuccessView.as_view(), name='feedback_success'),
]
