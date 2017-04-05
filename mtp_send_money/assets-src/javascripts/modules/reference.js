// Reference section
'use strict';

exports.Reference = {
  init: function () {
    $('.mtp-print-reference').click(function (e) {
      e.preventDefault();
      try {
        window.print();
      } catch (e) {}  // eslint-disable-line
    });
  }
};
