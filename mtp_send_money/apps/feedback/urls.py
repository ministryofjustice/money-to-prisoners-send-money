from django.conf import settings
from django.conf.urls import url
from django.core.urlresolvers import reverse_lazy
from zendesk_tickets import views

from .forms import CitizenFeedbackForm

urlpatterns = [
    url(r'^feedback/$', views.ticket,
        {
            'form_class': CitizenFeedbackForm,
            'template_name': 'mtp_common/feedback/submit_feedback.html',
            'success_redirect_url': reverse_lazy('feedback_success'),
            'subject': 'MTP Send Money Feedback',
            'tags': ['feedback', 'mtp', 'send-money', settings.ENVIRONMENT]
        }, name='submit_ticket'),
    url(r'^feedback/success/$', views.success,
        {
            'template_name': 'mtp_common/feedback/success.html',
        }, name='feedback_success'),
]
