"""
Content Security Policy: tells the browser where this site's pages may load scripts,
styles and images from, and that code written into a page itself must not run. If a
bug ever lets a visitor's text reach a page as HTML, the browser still refuses to run it.

Django 6 has this built in (ContentSecurityPolicyMiddleware, SECURE_CSP and
SECURE_CSP_REPORT_ONLY). The settings here have the same names and shape, so at that
upgrade this file goes and MIDDLEWARE points at Django's class.
"""

from django.conf import settings

HEADER = 'Content-Security-Policy'
REPORT_ONLY_HEADER = 'Content-Security-Policy-Report-Only'


def build_policy(policy):
    """{'img-src': ["'self'", 'data:']} -> "img-src 'self' data:"."""
    return '; '.join(f'{directive} {" ".join(sources)}' for directive, sources in policy.items())


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        for header, policy in (
            (HEADER, settings.SECURE_CSP),
            (REPORT_ONLY_HEADER, settings.SECURE_CSP_REPORT_ONLY),
        ):
            # A view may set a policy of its own
            if policy and header not in response:
                response[header] = build_policy(policy)
        return response
