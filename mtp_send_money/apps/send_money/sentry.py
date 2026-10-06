import re

# prisoner numbers and dates of birth are passed to the api in the query string of this path
PRISONER_VALIDITY_PATH = '/prisoner_validity/'
PRISONER_VALIDITY_QUERY = re.compile(r'(/prisoner_validity/)\?[^\s\'"]*')
# local variables in these modules hold personal details that senders entered
FORMS_MODULES = ('send_money.forms', 'mtp_send_money.apps.send_money.forms')


def scrub_prisoner_details(event, hint):
    """
    Sentry `before_send` hook that removes prisoner details from errors.
    Events that mention prisoner validity lookups have the query strings of those addresses dropped wherever they
    appear (exception messages, log messages and http breadcrumbs) and lose all local variables.
    Frames in form code always lose their local variables.
    """
    if PRISONER_VALIDITY_PATH in repr(event):
        return _scrub(event)

    stacktraces = [
        value.get('stacktrace')
        for key in ('exception', 'threads')
        for value in (event.get(key) or {}).get('values') or []
    ]
    for stacktrace in filter(None, stacktraces):
        for frame in stacktrace.get('frames') or []:
            if frame.get('module') in FORMS_MODULES:
                frame.pop('vars', None)
    return event


def _scrub(value):
    if isinstance(value, str):
        return PRISONER_VALIDITY_QUERY.sub(r'\1', value)
    if isinstance(value, dict):
        value = dict(value)
        # http breadcrumbs record the query string separately from the url
        if PRISONER_VALIDITY_PATH in str(value.get('url') or ''):
            value.pop('http.query', None)
            value.pop('http.fragment', None)
        value.pop('vars', None)
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(item) for item in value]
    return value
