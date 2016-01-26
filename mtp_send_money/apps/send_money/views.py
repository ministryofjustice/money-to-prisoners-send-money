from functools import wraps
import logging

from django.conf import settings
from django.core.urlresolvers import reverse, reverse_lazy
from django.shortcuts import redirect, render
from django.utils.translation import ugettext as _
from django.views.generic import FormView
import requests
from slumber.exceptions import SlumberHttpBaseException

from send_money.forms import PaymentMethod, SendMoneyForm
from send_money.utils import (
    unserialise_amount, unserialise_date, bank_transfer_reference,
    govuk_headers, govuk_url, get_api_client, site_url, get_link_by_rel,
    get_total_charge
)

logger = logging.getLogger('mtp')


def require_session_parameters(func):
    @wraps(func)
    def inner(request, *args, **kwargs):
        for required_key in SendMoneyForm.get_field_names():
            if not request.session.get(required_key):
                return redirect(reverse('send_money:send_money'))
        return func(request, *args, **kwargs)

    return inner


class SendMoneyView(FormView):
    form_class = SendMoneyForm
    template_name = 'send_money/send-money.html'
    success_url = reverse_lazy('send_money:send_money')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.extra_context = {
            'preview': False
        }

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        sample_amount = 20  # in pounds
        context_data.update({
            'service_charge_percentage': settings.SERVICE_CHARGE_PERCENTAGE,
            'service_charge_fixed': settings.SERVICE_CHARGE_FIXED,
            'sample_amount': sample_amount,
        })

        # TODO: remove option once TD allows showing bank transfers
        context_data['HIDE_BANK_TRANSFER_OPTION'] = settings.HIDE_BANK_TRANSFER_OPTION

        context_data.update(self.extra_context)
        return context_data

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        if 'next' in self.request.POST:
            # proceed
            return super().form_valid(form)
        if 'change' not in self.request.POST:
            # preview form
            self.extra_context['preview'] = True
            form.switch_to_hidden()
            form.save_form_data_in_session(self.request.session)
        # previewing or changing
        return self.form_invalid(form)

    def get_success_url(self):
        if self.request.session['payment_method'] == str(PaymentMethod.bank_transfer):
            return reverse('send_money:bank_transfer')
        return reverse('send_money:debit_card')


def make_context_from_session(session):
    context = {field: session[field] for field in SendMoneyForm.get_field_names()}
    context['prisoner_dob'] = unserialise_date(context['prisoner_dob'])
    context['amount'] = unserialise_amount(context['amount'])
    return context


@require_session_parameters
def bank_transfer_view(request):
    context = make_context_from_session(request.session)
    context.update({
        'payable_to': settings.NOMS_HOLDING_ACCOUNT_NAME,
        'account_number': settings.NOMS_HOLDING_ACCOUNT_NUMBER,
        'sort_code': settings.NOMS_HOLDING_ACCOUNT_SORT_CODE,
        'bank_transfer_reference': bank_transfer_reference(
            context['prisoner_number'],
            context['prisoner_dob'],
        ),
        'amount_to_pay': get_total_charge(request.session['amount']),
    })
    request.session.flush()
    return render(request, 'send_money/bank-transfer.html', context)


@require_session_parameters
def debit_card_view(request):
    context = make_context_from_session(request.session)

    new_payment = {
        'amount': int(context['amount']*100),
        'recipient_name': context['prisoner_name'],
        'prisoner_number': context['prisoner_number'],
        'prisoner_dob': context['prisoner_dob'].isoformat(),
    }

    client = get_api_client()
    try:
        api_response = client.payments.post(new_payment)
        payment_ref = api_response['uuid']

        new_govuk_payment = {
            'amount': int(context['amount']*100),
            'reference': payment_ref,
            'description': _('Payment to prisoner %(prisoner_number)s'
                             % {'prisoner_number': context['prisoner_number']}),
            'return_url': site_url(
                reverse('send_money:confirmation') + '?payment_ref=' + payment_ref
            ),
        }

        govuk_response = requests.post(
            govuk_url('/payments'), headers=govuk_headers(), json=new_govuk_payment
        )

        if govuk_response.status_code == 201:
            govuk_data = govuk_response.json()
            payment_update = {
                'processor_id': govuk_data['payment_id']
            }
            client.payments(payment_ref).patch(payment_update)
            return redirect(get_link_by_rel(govuk_data, 'next_url')['href'])
        else:
            logger.error(
                'Failed to create new GOV.UK payment for transaction %s'
                % api_response['uuid']
            )
    except SlumberHttpBaseException:
        logger.exception('Failed to create new payment')

    return render(request, 'send_money/failure.html', context)


def confirmation_view(request):
    payment_ref = request.GET.get('payment_ref')
    if payment_ref is None:
        return redirect(reverse('send_money:send_money'))
    context = {'success': False}

    try:
        client = get_api_client()
        api_response = client.payments(payment_ref).get()
        govuk_id = api_response['processor_id']

        govuk_response = requests.get(
            govuk_url('/payments/%s' % govuk_id), headers=govuk_headers()
        )

        if (govuk_response.status_code == 200 and
                govuk_response.json()['status'] == 'SUCCEEDED'):
            payment_update = {
                'status': 'taken'
            }

            client.payments(payment_ref).patch(payment_update)
            context['success'] = True
        else:
            logger.error(
                'Failed to retrieve payment status from GOV.UK for payment %s' % payment_ref
            )
    except SlumberHttpBaseException:
            logger.exception(
                'Failed to access payment %s' % payment_ref,
            )

    request.session.flush()
    return render(request, 'send_money/confirmation.html', context)


def clear_session_view(request):
    request.session.flush()
    return redirect('send_money:send_money')
