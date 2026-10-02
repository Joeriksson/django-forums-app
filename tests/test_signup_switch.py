import pytest
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.urls import reverse
from pytest_django.asserts import (
    assertContains,
    assertNotContains,
    assertRedirects,
    assertTemplateNotUsed,
    assertTemplateUsed,
)

User = get_user_model()
SIGNUP_DATA = {'email': 'newuser@example.com', 'password1': 'a-long-test-pass-123'}


@pytest.fixture
def signup_closed(settings):
    settings.SIGNUP_OPEN = False


@pytest.fixture
def signup_open(settings):
    settings.SIGNUP_OPEN = True


@pytest.mark.django_db
def test_closed_signup_page_says_closed(client, signup_closed):
    resp = client.get(reverse('account_signup'))

    assertTemplateUsed(resp, 'account/signup_closed.html')
    assertTemplateNotUsed(resp, 'account/signup.html')
    # In the site layout, not allauth's bare one
    assertTemplateUsed(resp, '_base.html')
    assertContains(resp, 'Sign up is closed')


@pytest.mark.django_db
def test_closed_signup_post_creates_no_user(client, signup_closed):
    resp = client.post(reverse('account_signup'), SIGNUP_DATA)

    assertTemplateUsed(resp, 'account/signup_closed.html')
    assert not User.objects.filter(email=SIGNUP_DATA['email']).exists()


@pytest.mark.django_db
def test_open_signup_creates_user(client, signup_open):
    client.post(reverse('account_signup'), SIGNUP_DATA)

    assert User.objects.filter(email=SIGNUP_DATA['email']).exists()


@pytest.mark.django_db
def test_login_works_while_signup_closed(client, signup_closed, verify_email):
    user = User.objects.create_user(
        username='member', email='member@example.com', password='a-long-test-pass-123'
    )
    verify_email(user)

    resp = client.post(
        reverse('account_login'),
        {'login': 'member@example.com', 'password': 'a-long-test-pass-123'},
    )

    assertRedirects(resp, reverse('home'), fetch_redirect_response=False)
    assert client.session['_auth_user_id'] == str(user.pk)


@pytest.mark.django_db
def test_closed_signup_refuses_new_github_user(client, github_login, signup_closed):
    resp = github_login('octocat@example.com')

    assertContains(resp, 'Sign up is closed')
    assert not User.objects.filter(email='octocat@example.com').exists()
    assert '_auth_user_id' not in client.session


@pytest.mark.django_db
def test_open_signup_creates_github_user(client, github_login, signup_open):
    github_login('octocat@example.com')

    user = User.objects.get(email='octocat@example.com')
    assert client.session['_auth_user_id'] == str(user.pk)


@pytest.mark.django_db
def test_existing_github_user_logs_in_while_signup_closed(
    client, github_login, signup_closed, verify_email
):
    user = User.objects.create_user(username='octocat', email='octocat@example.com')
    verify_email(user)
    SocialAccount.objects.create(user=user, provider='github', uid='12345')

    resp = github_login('octocat@example.com')

    assert resp.status_code == 302
    assert client.session['_auth_user_id'] == str(user.pk)
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_navbar_hides_signup_link_while_closed(client, signup_closed):
    resp = client.get(reverse('home'))

    assertContains(resp, reverse('account_login'))
    assertNotContains(resp, reverse('account_signup'))


@pytest.mark.django_db
def test_navbar_shows_signup_link_while_open(client, signup_open):
    resp = client.get(reverse('home'))

    assertContains(resp, reverse('account_signup'))


@pytest.mark.django_db
def test_server_error_page_renders_without_request(rf, signup_open):
    # Django renders 500.html without a request; the navbar must still render
    from django.views.defaults import server_error

    resp = server_error(rf.get('/'))

    assert resp.status_code == 500
    assert b'Log' in resp.content
