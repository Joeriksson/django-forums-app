"""The 403, 404 and 500 pages: the site's header, a title, one line and the way back."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.views.defaults import server_error
from pytest_django.asserts import assertContains, assertTemplateUsed

User = get_user_model()

# The header links home too; this is the page's own way back
BACK = f'<a class="button" href="{reverse("home")}">Back to the start</a>'


@pytest.mark.django_db
def test_page_not_found(client):
    resp = client.get('/no-such-page/')

    assert resp.status_code == 404
    assertTemplateUsed(resp, '404.html')
    assertContains(resp, '<h1>Page not found</h1>', status_code=404)
    assertContains(resp, 'class="site-header"', status_code=404)
    assertContains(resp, BACK, status_code=404)


@pytest.mark.django_db
def test_permission_denied(client):
    # Members have no permissions, and adding a forum needs one
    member = User.objects.create_user(username='m', email='m@example.com', password='x')
    client.force_login(member)

    resp = client.get(reverse('forum_add'))

    assert resp.status_code == 403
    assertTemplateUsed(resp, '403.html')
    assertContains(resp, '<h1>Not allowed</h1>', status_code=403)
    assertContains(resp, BACK, status_code=403)


@pytest.mark.django_db
def test_server_error(rf):
    # Django renders 500.html without a request or a user
    resp = server_error(rf.get('/'))

    assert resp.status_code == 500
    assert b'<h1>Something went wrong</h1>' in resp.content
    assert b'class="site-header"' in resp.content
    assert BACK.encode() in resp.content
