from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.http import is_safe_url
from django.utils.translation import override as override_language
from django.views.generic import TemplateView


def help_view(request):
    """
    FAQ section
    @param request: the HTTP request
    """
    context = {}
    return_to = request.META.get('HTTP_REFERER')
    if is_safe_url(url=return_to, host=request.get_host()) and return_to != request.build_absolute_uri():
        context['return_to'] = return_to
    return render(request, 'send_money/help.html', context=context)


def robots_txt_view(request):
    """
    robots.txt - blocks access on non-prod and refers to sitemap.xml
    @param request: the HTTP request
    """
    if settings.ENVIRONMENT == 'prod':
        robots_txt = 'User-agent: *\nDisallow: /'
    else:
        robots_txt = 'Sitemap: %s' % request.build_absolute_uri(reverse('sitemap_xml'))
    return HttpResponse(robots_txt, content_type='text/plain')


class SitemapXMLView(TemplateView):
    """
    sitemap.xml - links search engines to the main content pages
    """
    template_name = 'send_money/sitemap.xml'
    content_type = 'application/xml; charset=utf-8'

    def make_links(self):
        url_names = ['send_money:choose_method', 'send_money:help', 'send_money:prison_list']
        links = {}
        request = self.request
        for lang_code, lang_name in settings.LANGUAGES:
            with override_language(lang_code):
                links[lang_code] = {
                    url_name: request.build_absolute_uri(reverse(url_name))
                    for url_name in url_names
                }
        return (
            {
                'url': links[settings.LANGUAGE_CODE][url_name],
                'alt_links': (
                    {
                        'lang': lang_code,
                        'url': links[lang_code][url_name],
                    }
                    for lang_code, lang_name in settings.LANGUAGES
                ) if settings.SHOW_LANGUAGE_SWITCH else []
            }
            for url_name in url_names
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(links=self.make_links(), **kwargs)
