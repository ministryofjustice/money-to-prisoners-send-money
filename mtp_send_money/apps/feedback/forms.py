from django.conf import settings
from zendesk_tickets.forms import EmailTicketForm


class CitizenFeedbackForm(EmailTicketForm):
    def submit_ticket(self, request, subject, tags, ticket_template_name, requester_email=None, extra_context={}):
        if settings.START_PAGE_URL in (self.cleaned_data.get('referer') or ''):
            tags += ['citizen-info']
        return super().submit_ticket(request, subject, tags, ticket_template_name,
                                     requester_email=requester_email, extra_context=extra_context)
