import datetime
from decimal import Decimal
from functools import partial
import unittest

from django.core.exceptions import ValidationError
from django.test.utils import override_settings
from requests.exceptions import Timeout
import responses

from send_money.utils import (
    serialise_amount, unserialise_amount,
    serialise_date, unserialise_date, lenient_unserialise_date,
    format_percentage, currency_format, currency_format_pence,
    clamp_amount, get_service_charge, get_total_charge,
    RejectCardNumberValidator, validate_prisoner_number, bank_transfer_reference,
    api_url, check_payment_service_available,
)


class BaseEqualityTestCase(unittest.TestCase):
    def assertCaseEquality(self, function, cases, msg=None):  # noqa: N802
        if not cases:
            self.fail('No cases to test')
        msg = msg or 'Expected %(value)s to be %(expected)s'
        for value, expected in cases:
            self.assertEqual(function(value), expected,
                             msg=msg % {
                                 'value': value,
                                 'expected': expected,
                             })


class AmountSerialisationTestCase(BaseEqualityTestCase):
    def test_amount_serialisation(self):
        cases = [
            (Decimal('1'), '1.00'),
            (Decimal(1), '1.00'),
            (Decimal('1000'), '1000.00'),
        ]
        self.assertCaseEquality(serialise_amount, cases)

    def test_amount_unserialisation(self):
        cases = [
            ('1.00', Decimal('1')),
            ('1.00', Decimal('1.00')),
            ('1000.00', Decimal('1000')),
        ]
        self.assertCaseEquality(unserialise_amount, cases)


class DateSerialisationTestCase(BaseEqualityTestCase):
    def test_date_serialisation(self):
        cases = [
            (datetime.date(2015, 11, 14), '2015-11-14'),
            (datetime.date(2016, 1, 14), '2016-01-14'),
        ]

        self.assertCaseEquality(serialise_date, cases)

    def test_date_unserialisation(self):
        cases = [
            ('2015-11-14', datetime.date(2015, 11, 14)),
            ('2016-01-14', datetime.date(2016, 1, 14)),
        ]
        self.assertCaseEquality(unserialise_date, cases)

    def test_lenient_date_unserialisation(self):
        cases = [
            ('2015-11-14', datetime.date(2015, 11, 14)),
            ('2016-01-14', datetime.date(2016, 1, 14)),
            ('14/1/2016', datetime.date(2016, 1, 14)),
            ('14/01/2016', datetime.date(2016, 1, 14)),
        ]
        self.assertCaseEquality(lenient_unserialise_date, cases)


class PercentageFormatTestCase(BaseEqualityTestCase):
    def test_percentage_formatting(self):
        cases = [
            (10, '10%'),
            ('10', '10%'),
            (Decimal('10'), '10%'),
            (10 / 3, '3.3%'),
            ('3.33', '3.3%'),
            (Decimal('10') / 3, '3.3%'),
            (2 / 3, '0.7%'),
            ('0.66', '0.7%'),
        ]
        self.assertCaseEquality(format_percentage, cases)

        cases = [
            (10, '10%'),
            ('10', '10%'),
            (Decimal('10'), '10%'),
            (10 / 3, '3%'),
            ('3.33', '3%'),
            (Decimal('10') / 3, '3%'),
            (2 / 3, '1%'),
            ('0.66', '1%'),
        ]
        self.assertCaseEquality(partial(format_percentage, decimals=0), cases)

        cases = [
            (10 / 3, '3.33%'),
            ('3.33', '3.33%'),
            (Decimal('10') / 3, '3.33%'),
            (2 / 3, '0.67%'),
            ('0.66', '0.66%'),
        ]
        self.assertCaseEquality(partial(format_percentage, decimals=2), cases)


class CurrencyFormatTestCase(BaseEqualityTestCase):
    def test_currency_formatting(self):
        cases = [
            (0, '£0.00'),
            (1, '£1.00'),
            (100, '£100.00'),
            (1000, '£1000.00'),
            (123.45, '£123.45'),
            ('1', '£1.00'),
            ('1.00', '£1.00'),
            ('1.0', '£1.00'),
            ('123.45', '£123.45'),
            (Decimal(123.45), '£123.45'),
            (Decimal('123.45'), '£123.45'),
        ]
        self.assertCaseEquality(currency_format, cases,
                                'Expected %(value)s to format into %(expected)s')

        cases = [
            (0, '£0'),
            (1, '£1'),
            (1000, '£1000'),
            (123.45, '£123.45'),
            ('1', '£1'),
            ('1.00', '£1'),
            ('123.45', '£123.45'),
            (Decimal(123.45), '£123.45'),
            (Decimal('123.45'), '£123.45'),
        ]
        self.assertCaseEquality(partial(currency_format, trim_empty_pence=True), cases,
                                'Expected %(value)s to trimmed format into %(expected)s')

    def test_pence_currency_formatting(self):
        cases = [
            (0, '0p'),
            (0.01, '1p'),
            (0.99, '99p'),
            (1, '£1.00'),
            (123.45, '£123.45'),
        ]
        self.assertCaseEquality(currency_format_pence, cases,
                                'Expected %(value)s to pence format into %(expected)s')

        cases = [
            (0, '0p'),
            (0.01, '1p'),
            (0.99, '99p'),
            (1, '£1'),
            (123.45, '£123.45'),
        ]
        self.assertCaseEquality(partial(currency_format_pence, trim_empty_pence=True), cases,
                                'Expected %(value)s to trimmed pence format into %(expected)s')


class DecimalRoundingTestCase(BaseEqualityTestCase):
    def test_decimal_rounding(self):
        cases = [
            # no rounding necessary
            (Decimal('0'), Decimal('0')),
            (Decimal('1'), Decimal('1')),
            (Decimal('1.00'), Decimal('1.00')),
            (Decimal('-0'), Decimal('0')),
            (Decimal('-1'), Decimal('-1')),
            (Decimal('1.5'), Decimal('1.5')),
            (Decimal('1.01'), Decimal('1.01')),
            (Decimal('-1.01'), Decimal('-1.01')),

            # positive, rounded
            (Decimal('20.0005'), Decimal('20.00')),
            (Decimal('20.001'), Decimal('20.01')),
            (Decimal('20.004'), Decimal('20.01')),
            (Decimal('20.005'), Decimal('20.01')),
            (Decimal('20.009'), Decimal('20.01')),
            (Decimal('1') / Decimal('3'), Decimal('0.34')),
            (Decimal('2') / Decimal('3'), Decimal('0.67')),
            (Decimal('2.370'), Decimal('2.37')),
            (Decimal('2.375'), Decimal('2.38')),
            (Decimal('2.371'), Decimal('2.38')),
            (Decimal('2.3709'), Decimal('2.37')),
            (Decimal('2.37001'), Decimal('2.37')),

            # negative, rounded
            (Decimal('-20.0005'), Decimal('-20.00')),
            (Decimal('-20.001'), Decimal('-20.01')),
            (Decimal('-20.004'), Decimal('-20.01')),
            (Decimal('-20.005'), Decimal('-20.01')),
            (Decimal('-20.009'), Decimal('-20.01')),
            (Decimal('-1') / Decimal('3'), Decimal('-0.34')),
            (Decimal('-2') / Decimal('3'), Decimal('-0.67')),
            (Decimal('-2.370'), Decimal('-2.37')),
            (Decimal('-2.375'), Decimal('-2.38')),
            (Decimal('-2.371'), Decimal('-2.38')),
            (Decimal('-2.3709'), Decimal('-2.37')),
            (Decimal('-2.37001'), Decimal('-2.37')),
        ]
        self.assertCaseEquality(clamp_amount, cases,
                                'Expected %(value)s to round to %(expected)s')


class ServiceChargeTestCase(BaseEqualityTestCase):
    @classmethod
    def map_cases_to_expected_charges(cls, case):
        value, expected = case
        return value, clamp_amount(expected - Decimal(value))

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('0'),
                       SERVICE_CHARGE_FIXED=Decimal('0'))
    def test_no_service_charge(self):
        cases = [
            (0, Decimal('0')),
            (10, Decimal('10')),
            ('10', Decimal('10')),
            (120.40, Decimal('120.40')),
            ('120.40', Decimal('120.40')),
        ]
        self.assertCaseEquality(get_total_charge, cases,
                                'Expected %(value)s to be %(expected)s with no service charge')

        cases = map(self.map_cases_to_expected_charges, cases)
        self.assertCaseEquality(get_service_charge, cases,
                                'Expected %(value)s to have a service charge of %(expected)s'
                                ' with no service charge')

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('2.4'),
                       SERVICE_CHARGE_FIXED=Decimal('0'))
    def test_percentage_service_charge(self):
        cases = [
            (0, Decimal('0')),
            (10, Decimal('10.24')),
            ('10', Decimal('10.24')),
            (120.40, Decimal('123.29')),
            ('120.40', Decimal('123.29')),
        ]
        self.assertCaseEquality(get_total_charge, cases,
                                'Expected %(value)s to be %(expected)s with percentage service charge')

        cases = map(self.map_cases_to_expected_charges, cases)
        self.assertCaseEquality(get_service_charge, cases,
                                'Expected %(value)s to have a service charge of %(expected)s'
                                ' with percentage service charge')

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('0'),
                       SERVICE_CHARGE_FIXED=Decimal('0.20'))
    def test_fixed_service_charge(self):
        cases = [
            (0, Decimal('0.2')),
            (10, Decimal('10.2')),
            ('10', Decimal('10.2')),
            (120.40, Decimal('120.60')),
            ('120.40', Decimal('120.60')),
        ]
        self.assertCaseEquality(get_total_charge, cases,
                                'Expected %(value)s to be %(expected)s with fixed service charge')

        cases = map(self.map_cases_to_expected_charges, cases)
        self.assertCaseEquality(get_service_charge, cases,
                                'Expected %(value)s to have a service charge of %(expected)s'
                                ' with fixed service charge')

    @override_settings(SERVICE_CHARGE_PERCENTAGE=Decimal('2.4'),
                       SERVICE_CHARGE_FIXED=Decimal('0.20'))
    def test_both_service_charges(self):
        cases = [
            (0, Decimal('0.2')),
            (10, Decimal('10.44')),
            ('10', Decimal('10.44')),
            (120.40, Decimal('123.49')),
            ('120.40', Decimal('123.49')),
        ]
        self.assertCaseEquality(get_total_charge, cases,
                                'Expected %(value)s to be %(expected)s with both service charges')

        cases = map(self.map_cases_to_expected_charges, cases)
        self.assertCaseEquality(get_service_charge, cases,
                                'Expected %(value)s to have a service charge of %(expected)s'
                                ' with both service charges')


class ValidationTestCase(unittest.TestCase):
    def test_valid_prisoner_number_validation(self):
        validate_prisoner_number('A1234AB')
        # case is ignored, but number is sent to api as uppercase
        validate_prisoner_number('a1234ab')

    def test_invalid_prisoner_number_validation(self):
        with self.assertRaises(ValidationError):
            validate_prisoner_number('')
        with self.assertRaises(ValidationError):
            validate_prisoner_number('1234567')

    def test_card_number_validation(self):
        validator = RejectCardNumberValidator()
        invalid = [
            '4444333322221111',
            ' 4444333322221111 ',
            '4444 3333 2222 1111',
            ' 4444  33332222 1111',
            'Lorem ipsum 4444333322221111 dolor sit amet',
            'Lorem ipsum 4444 3333\n2222 1111 dolor sit amet',
            '4462030000000000',
            '4917610000000000003',
            '6759649826438453',
            '6799990100000000019',
            '5555555555554444',
            '5454545454545454',
            '4917300800000000',
        ]
        for sample in invalid:
            with self.assertRaises(ValidationError, msg='“%s” should raise a card number validation error' % sample):
                validator(sample)


class BankTransferReference(unittest.TestCase):
    def test_bank_transfer_reference(self):
        self.assertEqual(
            bank_transfer_reference('AB1234AB', datetime.date(1980, 1, 4)),
            'AB1234AB/04/01/80',
        )


class PaymentServiceAvailabilityTestCase(unittest.TestCase):
    def test_passed_healthcheck_returns_true(self):
        with responses.RequestsMock() as rsps:
            rsps.add(rsps.GET, api_url('/service-availability/'), json={'gov_uk_pay': {'status': True}})
            available, message_to_users = check_payment_service_available()
        self.assertTrue(available)
        self.assertIsNone(message_to_users)

    def test_healthcheck_timeout_returns_true(self):
        with responses.RequestsMock() as rsps:
            rsps.add(rsps.GET, api_url('/service-availability/'), body=Timeout())
            available, message_to_users = check_payment_service_available()
        self.assertTrue(available)
        self.assertIsNone(message_to_users)

    def test_failed_healthcheck_returns_true(self):
        with responses.RequestsMock() as rsps:
            rsps.add(rsps.GET, api_url('/service-availability/'), body=b'Server error', status=500)
            available, message_to_users = check_payment_service_available()
        self.assertTrue(available)
        self.assertIsNone(message_to_users)

    def test_healthcheck_with_service_unspecified_returns_true(self):
        with responses.RequestsMock() as rsps:
            rsps.add(rsps.GET, api_url('/service-availability/'), json={'another_service': {'status': False}})
            available, message_to_users = check_payment_service_available()
        self.assertTrue(available)
        self.assertIsNone(message_to_users)

    def test_healthcheck_with_service_down_returns_false(self):
        with responses.RequestsMock() as rsps:
            rsps.add(rsps.GET, api_url('/service-availability/'), json={'gov_uk_pay': {'status': False}})
            available, message_to_users = check_payment_service_available()
        self.assertFalse(available)
        self.assertIsNone(message_to_users)

    def test_healthcheck_with_service_down_returns_message_to_users(self):
        with responses.RequestsMock() as rsps:
            rsps.add(rsps.GET, api_url('/service-availability/'), json={
                'gov_uk_pay': {'status': False, 'message_to_users': 'Scheduled downtime'}
            })
            available, message_to_users = check_payment_service_available()
        self.assertFalse(available)
        self.assertEqual(message_to_users, 'Scheduled downtime')
