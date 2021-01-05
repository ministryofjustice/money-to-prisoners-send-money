'use strict';

export var ServiceCharge = {
  init: function (selector) {
    selector = selector || '.mtp-service-charge';
    var instance = this;

    $(selector).each(function () {
      var $container = $(this);
      var $input = $container.find('.mtp-amount-input');
      var $charges = $container.find('.mtp-service-charge__service-charge');
      var $total = $container.find('.mtp-service-charge__total');
      var proportionalCharge = Number($container.data('percentage-charge')) / 100;
      var fixedCharge = Number($container.data('fixed-charge'));

      var update = function () {
        var valid = false;
        var amount = $input.val();
        if (/^ *\d+(\.\d{2})? *$/.test(amount)) {
          amount = Number(amount);
          if (amount > 0) {
            var serviceCharge = this.round(amount * proportionalCharge + fixedCharge);
            $charges.text(this.formatAsPrice(serviceCharge));
            $total.text(this.formatAsPrice(amount + this.round(serviceCharge)));
            valid = true;
          }
        }
        if (!valid) {
          $charges.text('');
          $total.text('');
        }
      };
      update = $.proxy(update, instance);
      $input.on('keyup change click', update);
      update();
    });
  },

  formatAsPrice: function (amount) {
    return '£' + amount.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  },

  // Applies the rounding algorithm we use:
  // 1. discard all decimal digits after the 3rd place (excluded)
  // 2. round up
  round: function (amount) {
    amount = amount * 100;
    return Math.ceil(Number(amount.toString().replace(/(\.\d)\d*/, '$1'))) / 100;
  }
};
