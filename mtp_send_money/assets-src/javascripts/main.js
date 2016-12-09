(function () {
  'use strict';

  require('proposition-header').PropositionHeader.init();
  require('analytics').Analytics.init();
  require('element-focus').ElementFocus.init();
  require('year-field-completion').YearFieldCompletion.init();
  require('help-popup').HelpPopup.init();
  require('print').Print.init();
  require('charges').Charges.init();
  require('experiments').Experiments.init();
  require('reference').Reference.init();
  require('greyout').Greyout.init();
  require('filtered-list').FilteredList.init();
  require('placeholder-polyfill').PlaceholderPolyfill.init();
  require('selection-buttons').SelectionButtons.init();
}());
