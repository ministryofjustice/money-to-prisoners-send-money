import logging

from django.views.generic import TemplateView

logger = logging.getLogger()


class SendMoneyView(TemplateView):
    template_name = 'send_money/send-money.html'
