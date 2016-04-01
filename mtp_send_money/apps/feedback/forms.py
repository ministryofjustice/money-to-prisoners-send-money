from django.conf import settings
from zendesk_tickets.forms import EmailTicketForm


class CitizenFeedbackForm(EmailTicketForm):
    def submit_ticket(self, request, subject, tags,
                      ticket_template_name, extra_context={}):
        referer = self.cleaned_data.get('referer', None)
        if referer and settings.CITIZEN_INFO_URL in referer:
            tags += ['citizen-info']
        return super().submit_ticket(request, subject, tags,
                                     ticket_template_name, extra_context)
