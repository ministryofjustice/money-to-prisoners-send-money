// Charges module
// Automatically shows service charges when typing an amount in the payment page
/* globals require, exports, $ */
'use strict';

exports.Charges = {
  selector: '.mtp-amount',

  init: function () {
    var $jsSection = $(this.selector + ' .mtp-charges-js');
    var $noJsSection = $(this.selector + ' .mtp-charges-no-js');
    var $input = $(this.selector + ' .mtp-charges-amount');

    this.percentageCharge = $input.data('percentage-charge');
    this.fixedCharge = $input.data('fixed-charge');

    this.$charges = $(this.selector + ' .mtp-charges-charges');
    this.$total = $(this.selector + ' .mtp-charges-total span');

    if ($jsSection.length) {
      $jsSection.show();
      $noJsSection.hide();
      $input.on('keyup', $.proxy(this._updateTotal, this));
    }
  },

  _formatAsPrice: function(num) {
    return '£' + num.toFixed(2).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  },

  _updateTotal: function (event) {
    var amount = event.target.value;
    var serviceCharge;
    if (/^\d+(\.\d{1,2})?$/.test(amount)) {
      amount = Number(amount);
      serviceCharge = (amount * this.percentageCharge + this.fixedCharge) / 100;
      this.$charges.text(this._formatAsPrice(serviceCharge));
      this.$total.text(this._formatAsPrice(amount + serviceCharge));
    } else {
      this.$charges.text('');
      this.$total.text('');
    }
  }
};
