'use strict';

// design systems
import {initAll} from 'govuk-frontend';
initAll();

// mtp common components
import {initDefaults} from 'mtp_common';
import {YearFieldCompletion} from 'mtp_common/components/year-field-completion';
initDefaults();
YearFieldCompletion.init();
