from django.conf import settings
from django.urls import reverse_lazy, re_path
from django.views.generic import RedirectView

from help_area import views


app_name = 'help_area'
urlpatterns = [
    re_path(
        r'^help/$',
        views.HelpView.as_view(
            template_name='help_area/help.html',
            back_url=settings.START_PAGE_URL,
        ),
        name='help',
    ),
    re_path(
        r'^help/with-making-a-payment/$',
        views.HelpView.as_view(
            template_name='help_area/help-new-payment.html',
            back_url=reverse_lazy('help_area:help'),
        ),
        name='help-new-payment',
    ),
    re_path(
        r'^help/with-a-payment-i-sent/$',
        views.HelpView.as_view(
            template_name='help_area/help-sent-payment.html',
            back_url=reverse_lazy('help_area:help'),
        ),
        name='help-sent-payment',
    ),
    re_path(
        r'^help/cannot-access/$',
        views.HelpView.as_view(
            template_name='help_area/help-cannot-access.html',
            back_url=reverse_lazy('help_area:help'),
        ),
        name='help-cannot-access',
    ),
    re_path(
        r'^help/setup-basic-bank-account/$',
        views.HelpView.as_view(
            template_name='help_area/help-setup-basic-bank-account.html',
            back_url=reverse_lazy('help_area:help-cannot-access'),
        ),
        name='help-setup-basic-bank-account',
    ),
    re_path(
        r'^help/apply-for-exemption/$',
        views.HelpView.as_view(
            template_name='help_area/help-apply-for-exemption.html',
            back_url=reverse_lazy('help_area:help-cannot-access'),
        ),
        name='help-apply-for-exemption',
    ),

    re_path(
        r'^help/bank-transfer-issues/$',
        RedirectView.as_view(url=reverse_lazy('help_area:help-sent-payment'), permanent=True),
    ),
    re_path(
        r'^help/payment-delay/$',
        RedirectView.as_view(url=reverse_lazy('help_area:help-sent-payment'), permanent=True),
    ),
    re_path(
        r'^help/prisoner-moved-or-released/$',
        RedirectView.as_view(url=reverse_lazy('help_area:help-sent-payment'), permanent=True),
    ),

    re_path(r'^help/prisons/$', views.PrisonListView.as_view(), name='prison_list'),

    re_path(
        r'^contact-us/$',
        RedirectView.as_view(url=reverse_lazy('help_area:help'), permanent=False),
        name='submit_ticket',
    ),
    re_path(
        r'^contact-us/success/$',
        views.ContactSuccessView.as_view(),
        name='feedback_success',
    ),
    re_path(
        r'^help/with-making-a-payment/contact-us/$',
        views.ContactNewPaymentView.as_view(),
        name='contact-us-new-payment',
    ),
    re_path(
        r'^help/with-a-payment-i-sent/contact-us/$',
        views.ContactSentPaymentView.as_view(),
        name='contact-us-sent-payment',
    ),
]
