import re

# prisoner numbers and dates of birth are passed to the api in the query string of this path
PRISONER_VALIDITY_PATH = '/prisoner_validity/'
PRISONER_VALIDITY_QUERY = re.compile(r'(/prisoner_validity/)\?[^\s\'"]*')


def scrub_prisoner_details(event, hint):
    """
    Sentry `before_send` hook that removes prisoner details from errors.
    Events that mention prisoner validity lookups have the query strings of those addresses dropped wherever they
    appear (exception messages, log messages and http breadcrumbs).
    Local variables are not sent at all, see `include_local_variables` in settings.
    """
    if PRISONER_VALIDITY_PATH in repr(event):
        return _scrub(event)
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
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(item) for item in value]
    return value
