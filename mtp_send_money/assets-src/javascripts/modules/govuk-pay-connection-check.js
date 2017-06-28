// Try to load an image from GOV.UK Pay site to determine if user agent can connect
/* globals Raven */
'use strict';

exports.GOVUKPayConnectionCheck = {
  selector: '.mtp-govuk-pay-connection-check',

  init: function () {
    this.$container = $(this.selector);
    if (this.$container.length) {
      this.url = this.$container.data('image-url');
      this.connectionFailed = $.proxy(this.connectionFailed, this);
      this.connectionSucceeded = $.proxy(this.connectionSucceeded, this);
      this.checkConnection(1);
    }
  },

  checkConnection: function (retries) {
    var image = new Image();
    var failed = this.connectionFailed;
    image.onerror = function () {
      failed(retries);
    };
    image.onload = this.connectionSucceeded;
    image.src = this.url;
  },

  connectionFailed: function (retries) {
    if (retries > 0) {
      this.checkConnection(retries - 1);
      return;
    }
    this.$container.show();
    $('#id_debit_card').prop('checked', false).prop('disabled', true).parent().addClass('mtp-grey-choice');
    $('#id_bank_transfer').prop('checked', true);

    if (Raven) {
      Raven.captureMessage(
        'User agent ' + window.navigator.userAgent + ' cannot load GOV.UK Pay check image ' + this.url,
        {level: 'warning'}
      );
    }
  },

  connectionSucceeded: function () {
    this.$container.remove();
    $('#id_debit_card').prop('disabled', false).parent().removeClass('mtp-grey-choice');
  }
};
