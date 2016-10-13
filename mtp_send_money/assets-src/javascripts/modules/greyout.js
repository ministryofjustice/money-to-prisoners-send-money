// Greyout debit card choice when unavailable
/* globals exports, $ */
'use strict';

exports.Greyout = {

  init: function () {

    if ($('.error-summary').length) {
      var $blockLabel = $('.block-label:first');
      var $debitCardHeader = $('.mtp-debit-header');

      $blockLabel.addClass('mtp-grey-choice');
      $debitCardHeader.addClass('mtp-grey-text');
    }
  }
};