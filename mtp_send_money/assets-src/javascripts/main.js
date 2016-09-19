/* globals require */

(function() {
  'use strict';

  require('analytics').Analytics.init();
  require('element-focus').ElementFocus.init();
  require('year-field-completion').YearFieldCompletion.init();
  require('help-popup').HelpPopup.init();
  require('print').Print.init();

  require('charges').Charges.init();
  require('experiments').Experiments.init();
  require('reference').Reference.init();

})();
