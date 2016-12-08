// Reference section
'use strict';

exports.Reference = {
  init: function () {
    $('.mtp-print-reference').click(function (e) {
      e.preventDefault();
      window.print();
    });
    $('.mtp-email-reference').click(function (e) {
      e.preventDefault();
      $('#mtp-email-reference-form').show();
      $('#id_email').focus();
    });
  }
};
