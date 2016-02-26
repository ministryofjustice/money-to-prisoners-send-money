from django import forms
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from zendesk_tickets.forms import BaseTicketForm


class CitizenFeedbackForm(BaseTicketForm):
    ticket_content = forms.CharField(
        label=_('Tell us what you think about this service and help us improve.'),
        widget=forms.Textarea
    )
    contact_email = forms.EmailField(
        label=_('Your email address'), required=False
    )

    def submit_ticket(self, request, subject, tags,
                      ticket_template_name, extra_context={}):
        extra_context = dict(extra_context, **{
            'user_agent': request.META.get('HTTP_USER_AGENT')
        })
        if self.referer and settings.CITIZEN_INFO_URL in self.referer:
            tags.append('citizen-info')
        return super().submit_ticket(request, subject, tags,
                                     ticket_template_name, extra_context)
