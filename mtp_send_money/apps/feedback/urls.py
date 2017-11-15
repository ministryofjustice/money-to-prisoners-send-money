from django.conf import settings
from django.conf.urls import url
from django.urls import reverse_lazy
from django.views.generic import RedirectView
from zendesk_tickets import views

from feedback.forms import ContactForm

urlpatterns = [
    url(r'^feedback/$', RedirectView.as_view(url=reverse_lazy('submit_ticket'))),
    url(r'^contact-us/$', views.ticket,
        {
            'form_class': ContactForm,
            'template_name': 'send_money/contact-form.html',
            'ticket_template_name': 'send_money/contact-form-ticket.txt',
            'success_redirect_url': reverse_lazy('feedback_success'),
            'subject': 'MTP Send Money Feedback',
            'tags': ['feedback', 'mtp', 'send-money', settings.ENVIRONMENT],
        }, name='submit_ticket'),
    url(r'^contact-us/success/$', views.success,
        {
            'template_name': 'send_money/contact-form-success.html',
        }, name='feedback_success'),
]
