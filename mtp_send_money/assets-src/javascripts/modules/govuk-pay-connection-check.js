// Try to load an image from GOV.UK Pay site to determine if user agent can connect
/* globals Raven */
'use strict';

exports.GOVUKPayConnectionCheck = {
  selector: '.mtp-govuk-pay-connection-check',
  timeout: 10000,

  init: function () {
    this.$container = $(this.selector);
    if (this.$container.length) {
      this.url = this.$container.data('image-url');
      this.connectionFailed = $.proxy(this.connectionFailed, this);
      this.connectionSucceeded = $.proxy(this.connectionSucceeded, this);
      this.checkConnection();
    }
  },

  checkConnection: function () {
    var image = new Image();
    image.onerror = this.connectionFailed;
    image.onload = this.connectionSucceeded;
    image.src = this.url;
    this.timer = setTimeout(this.connectionFailed, this.timeout);
  },

  connectionFailed: function () {
    this.$container.show();
    $('#id_debit_card').prop('checked', false).prop('disabled', true).parent().addClass('mtp-grey-choice');
    $('#id_bank_transfer').prop('checked', true);

    if (Raven) {
      var message = 'User agent ' + window.navigator.userAgent + ' cannot load GOV.UK Pay check image ' + this.url;
      Raven.captureMessage(message, {level: 'warning'});
    }
  },

  connectionSucceeded: function () {
    clearTimeout(this.timer);
    this.$container.remove();
    $('#id_debit_card').prop('disabled', false).parent().removeClass('mtp-grey-choice');
  }
};
