from django.conf import settings
from django.conf.urls import url
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import RedirectView
from mtp_common.views import GetHelpView as BaseGetHelpView, GetHelpSuccessView as BaseGetHelpSuccessView

from feedback.forms import ContactForm


class GetHelpView(BaseGetHelpView):
    form_class = ContactForm
    success_url = reverse_lazy('feedback_success')
    template_name = 'send_money/contact-form.html'
    ticket_subject = 'MTP for Family Services - Send money to someone in prison'
    ticket_tags = ['feedback', 'mtp', 'send-money', settings.ENVIRONMENT]
    ticket_template_name = 'send_money/contact-form-ticket.txt'

    def get_context_data(self, **kwargs):
        kwargs['get_help_title'] = _('Contact us')
        return super().get_context_data(**kwargs)


class GetHelpSuccessView(BaseGetHelpSuccessView):
    template_name = 'send_money/contact-form-success.html'

    def get_context_data(self, **kwargs):
        kwargs['get_help_title'] = _('Contact us')
        return super().get_context_data(**kwargs)


urlpatterns = [
    url(r'^feedback/$', RedirectView.as_view(url=reverse_lazy('submit_ticket'))),
    url(r'^contact-us/$', GetHelpView.as_view(), name='submit_ticket'),
    url(r'^contact-us/success/$', GetHelpSuccessView.as_view(), name='feedback_success'),
]
