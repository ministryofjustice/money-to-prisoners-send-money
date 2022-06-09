import textwrap

from mtp_common.notify.templates import NotifyTemplateRegistry


class SendMoneyNotifyTemplates(NotifyTemplateRegistry):
    """
    Templates that mtp-send-money expects to exist in GOV.UK Notify
    """
    templates = {
        'send-money-debit-card-confirmation': {
            'subject': 'Send money to someone in prison: your payment was successful',
            'body': textwrap.dedent("""
                Dear sender,

                Your payment has been successful. Your confirmation number is ((short_payment_ref)).
                Money should reach the prisoner’s account in up to 3 working days.

                Payment to: ((prisoner_name))
                Amount: ((amount))
                Date payment made: ((today))

                Thank you for using this service.

                Help with problems using this service: ((help_url))
                Back to the service: ((site_url))
            """).strip(),
            'personalisation': [
                'short_payment_ref', 'prisoner_name', 'amount',
                'today',
                'site_url', 'help_url',
            ],
        },
        'send-money-debit-card-payment-on-hold': {
            'subject': 'Send money to someone in prison: your payment is being processed',
            'body': textwrap.dedent("""
                Dear sender,

                This payment is being processed.

                Payment to: ((prisoner_name))
                Amount: ((amount))
                Reference: ((short_payment_ref))

                We’ll email you a payment update in a few days. Please don’t contact us until you have it.

                Kind regards,
                Prisoner money compliance team
            """).strip(),
            'personalisation': [
                'short_payment_ref', 'prisoner_name', 'amount',
            ],
        },
        'send-money-debit-card-payment-accepted': {
            'subject': 'Send money to someone in prison: your payment has now gone through',
            'body': textwrap.dedent("""
                Dear sender,

                This payment has now gone through.

                Payment to: ((prisoner_name))
                Amount: ((amount))
                Confirmation number: ((short_payment_ref))

                We’re emailing to let you know that this payment has now been processed
                and will reach the prisoner’s account in one working day.

                Thank you for your patience.

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'short_payment_ref', 'prisoner_name', 'amount',
            ],
        },
        'send-money-debit-card-payment-rejected': {
            'subject': 'Send money to someone in prison: your payment has NOT been sent to the prisoner',
            'body': textwrap.dedent("""
                Dear sender,

                This payment has NOT been sent to the prisoner.

                Payment to: ((prisoner_name))
                Amount: ((amount))
                Reference: ((short_payment_ref))

                We’re emailing to tell you this payment has not passed our compliance check.
                HMPPS is committed to maintaining prison safety and security
                and because this payment may compromise this, we have been unable to process it.

                What now?
                Your debit card payment has not been taken from your account.
                If you need further assistance with this, please contact us at: ((compliance_contact))

                We’re sorry for any inconvenience this may have caused.

                Kind regards,
                Prisoner money compliance team
            """).strip(),
            'personalisation': [
                'short_payment_ref', 'prisoner_name', 'amount',
                'compliance_contact',
            ],
        },
        'send-money-debit-card-payment-timeout': {
            'subject': 'Send money to someone in prison: payment session expired',
            'body': textwrap.dedent("""
                Dear sender,

                We’re sorry to tell you that the payment session expired before your payment could be taken.
                This payment has not gone through to the prisoner’s account.

                Payment to: ((prisoner_name))
                Amount: ((amount))
                Reference: ((short_payment_ref))

                What now?
                Please go to Send money to someone in prison and try again: ((site_url))

                We’re sorry for any inconvenience this may have caused
                but we’re keen to keep the service running smoothly.
                Contact us if this is a recurring problem for you or if you need further help: ((help_url))

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'short_payment_ref', 'prisoner_name', 'amount',
                'site_url', 'help_url',
            ],
        },
    }
