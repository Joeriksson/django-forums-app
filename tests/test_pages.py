from django.urls import resolve, reverse
from pytest_django.asserts import assertContains, assertNotContains, assertTemplateUsed

from pages.views import HomePageView


def test_homepage(client):
    resp = client.get(reverse('home'))

    assert resp.status_code == 200
    assertTemplateUsed(resp, 'home.html')
    assertContains(resp, 'Homepage')
    assertNotContains(resp, 'This should not be on the page')


def test_homepage_url_resolves_homepageview():
    # as_view() functions are all named 'view', so compare the view class
    assert resolve('/').func.view_class is HomePageView
