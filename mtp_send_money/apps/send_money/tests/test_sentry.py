import copy

from django.test import SimpleTestCase

from send_money.sentry import scrub_prisoner_details

API_URL = 'http://api.local/prisoner_validity/'
QUERY = 'prisoner_number=A1231DE&prisoner_dob=1980-10-04'


def make_frames(module='send_money.views'):
    return [
        {'module': 'send_money.views', 'function': 'post', 'vars': {'self': '<PrisonerDetailsView>'}},
        {'module': module, 'function': 'is_prisoner_known',
         'vars': {'prisoner_number': "'A1231DE'", 'prisoner_dob': "'1980-10-04'"}},
    ]


def make_lookup_error_event():
    message = f'Status code 500 for {API_URL}?{QUERY}'
    return {
        'logentry': {'message': 'Could not look up prisoner validity: %s', 'params': [message]},
        'exception': {'values': [{
            'type': 'HttpServerError',
            'value': message,
            'stacktrace': {'frames': make_frames()},
        }]},
        'threads': {'values': [{'id': 1, 'stacktrace': {'frames': make_frames()}}]},
        'breadcrumbs': {'values': [
            {'type': 'http', 'category': 'httplib', 'data': {
                'url': API_URL, 'http.method': 'GET', 'http.query': QUERY, 'http.fragment': '', 'status_code': 500,
            }},
            {'type': 'http', 'category': 'httplib', 'data': {
                'url': 'http://api.local/prisoner_account_balances/A1231DE', 'http.method': 'GET',
                'http.query': '', 'status_code': 200,
            }},
        ]},
        'request': {'url': 'http://send-money.local/debit-card/prisoner-details/', 'method': 'POST'},
    }


class ScrubPrisonerDetailsTestCase(SimpleTestCase):
    def assertNoPrisonerDetails(self, event):  # noqa: N802
        self.assertNotIn('A1231DE&', str(event))
        self.assertNotIn("'A1231DE'", str(event))
        self.assertNotIn('1980-10-04', str(event))

    def test_prisoner_details_removed_from_lookup_errors(self):
        event = scrub_prisoner_details(make_lookup_error_event(), {})

        self.assertNoPrisonerDetails(event)
        self.assertEqual(event['exception']['values'][0]['value'], f'Status code 500 for {API_URL}')
        self.assertEqual(event['logentry']['params'], [f'Status code 500 for {API_URL}'])
        breadcrumb_data = event['breadcrumbs']['values'][0]['data']
        self.assertEqual(breadcrumb_data, {'url': API_URL, 'http.method': 'GET', 'status_code': 500})
        for key in ('exception', 'threads'):
            frames = event[key]['values'][0]['stacktrace']['frames']
            self.assertEqual([frame['function'] for frame in frames], ['post', 'is_prisoner_known'])
            self.assertFalse(any('vars' in frame for frame in frames))

    def test_other_breadcrumbs_kept(self):
        event = scrub_prisoner_details(make_lookup_error_event(), {})
        self.assertEqual(event['breadcrumbs']['values'][1], make_lookup_error_event()['breadcrumbs']['values'][1])

    def test_form_variables_removed_from_other_errors(self):
        event = {
            'exception': {'values': [{
                'type': 'TypeError',
                'value': 'unexpected value',
                'stacktrace': {'frames': make_frames(module='send_money.forms')},
            }]},
        }
        event = scrub_prisoner_details(event, {})

        self.assertNoPrisonerDetails(event)
        frames = event['exception']['values'][0]['stacktrace']['frames']
        self.assertEqual(frames[0]['vars'], {'self': '<PrisonerDetailsView>'})
        self.assertNotIn('vars', frames[1])

    def test_unrelated_errors_unchanged(self):
        event = {
            'exception': {'values': [{
                'type': 'HttpServerError',
                'value': 'Status code 500 for http://api.local/payments/?status=pending',
                'stacktrace': {'frames': [{'module': 'send_money.views', 'function': 'get', 'vars': {'a': '1'}}]},
            }]},
            'breadcrumbs': {'values': [
                {'type': 'http', 'data': {'url': 'http://api.local/payments/', 'http.query': 'status=pending'}},
            ]},
        }
        self.assertEqual(scrub_prisoner_details(copy.deepcopy(event), {}), event)

    def test_events_without_exceptions_unchanged(self):
        event = {'message': 'Something went wrong', 'level': 'error'}
        self.assertEqual(scrub_prisoner_details(copy.deepcopy(event), {}), event)
