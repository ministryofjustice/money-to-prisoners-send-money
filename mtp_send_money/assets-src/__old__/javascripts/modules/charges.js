// Charges module
// Automatically shows service charges when typing an amount in the payment page
'use strict';

exports.Charges = {
  selector: '.mtp-amount',

  init: function () {
    var $jsSection = $(this.selector + ' .mtp-charges-js');
    var $noJsSection = $(this.selector + ' .mtp-charges-no-js');
    var $input = $(this.selector + ' .mtp-charges-amount');

    this.percentageCharge = Number($input.data('percentage-charge')) / 100;
    this.fixedCharge = Number($input.data('fixed-charge'));

    this.$charges = $(this.selector + ' .mtp-charges-charges');
    this.$total = $(this.selector + ' .mtp-charges-total span');

    var updateTotal = $.proxy(this._updateTotal, this);

    if ($jsSection.length) {
      $jsSection.show();
      $noJsSection.hide();
      $input.on('keyup', function (event) {
        updateTotal(event.target.value);
      });
      updateTotal($input.val());
    }
  },

  _formatAsPrice: function (num) {
    return '£' + num.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  },

  // Applies the rounding algorithm we use:
  // 1. discard all decimal digits after the 3rd place (excluded)
  // 2. round up
  _round: function (num) {
    num = num * 100;
    return Math.ceil(Number(num.toString().replace(/(\.\d)\d*/, '$1'))) / 100;
  },

  _updateTotal: function (amount) {
    if (/^ *\d+(\.\d{2})? *$/.test(amount)) {
      var serviceCharge = this._round(Number(amount) * this.percentageCharge + this.fixedCharge);
      this.$charges.text(this._formatAsPrice(serviceCharge));
      this.$total.text(this._formatAsPrice(Number(amount) + this._round(serviceCharge)));
    } else {
      this.$charges.text('');
      this.$total.text('');
    }
  }
};
