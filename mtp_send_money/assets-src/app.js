'use strict';

// design systems
import {initAll} from 'govuk-frontend';
initAll();

// mtp common components
import {initDefaults} from 'mtp_common';
import {AccordionDirectLink} from 'mtp_common/components/accordion';
import {YearFieldCompletion} from 'mtp_common/components/year-field-completion';
initDefaults();
AccordionDirectLink.init();
YearFieldCompletion.init();

// app components
import {FilteredList} from './components/filtered-list';
import {Reference} from './components/reference-page';
import {ServiceCharge} from './components/service-charge';
FilteredList.init();
Reference.init();
ServiceCharge.init();
