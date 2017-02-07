// Sticky page contents menu
'use strict';

exports.StickyContents = {

  init: function () {
    if ($('.mtp-help__contents').length) {
      this.cacheEls();
      this.bindEvents();
    }
  },

  bindEvents: function () {
    this.$window.scroll($.proxy(this.stickContents, this));
    this.$window.scroll($.proxy(this.highlightActiveSectionLink, this));
  },

  cacheEls: function () {
    this.$window = $(window);
    this.$contents = $('.mtp-help__contents');
    this.contentsTopOffset = this.$contents.offset().top;
  },

  stickContents: function () {
    var y = this.$window.scrollTop();
    if (y >= this.contentsTopOffset) {
      this.$contents.addClass('mtp-help-contents--fixed');
    } else {
      this.$contents.removeClass('mtp-help-contents--fixed');
    }
  },

  highlightActiveSectionLink: function () {
    var scrollPosition = this.$window.scrollTop();
    var $navigationLinks = $('.mtp-help__contents-list > li > a');
    var $sections = $($(".mtp-help__section").get().reverse());
    var sectionIdToNavigationLink = {};

    $sections.each(function() {
      var currentSection = $(this);
      var sectionTop = currentSection.offset().top -20;
      var id = $(this).attr('id');

      sectionIdToNavigationLink[id] = $('.mtp-help__contents-list > li > a[href=#' + id + ']');

      if (scrollPosition >= sectionTop) {
        var $navigationLink = sectionIdToNavigationLink[id];
        if (!$navigationLink.hasClass('mtp-help__contents-list--active')) {
          $navigationLinks.removeClass('mtp-help__contents-list--active');
          $navigationLink.addClass('mtp-help__contents-list--active');
        }
        return false;
      }
    });
  },
}