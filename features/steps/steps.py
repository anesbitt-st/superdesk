
from behave import *
from flask import json

from tests import app

def test_json(context):
    response_data = json.loads(context.response.get_data())
    context_data = json.loads(context.text)
    for key in context_data:
        assert key in response_data and response_data[key] == context_data[key], key

def get_self_href(resource):
    href = resource['_links']['self']['href']
    return href.replace(app.config.get('SERVER_NAME'), '')

def get_res(url, context):
    return json.loads(context.client.get(url, follow_redirects=True).get_data())

@given('no user')
def step_impl(context):
    pass

@given('users')
def step_impl(context):
    with app.test_request_context():
        app.data.remove('users')
        users = [json.loads(user) for user in context.text.split(',')]
        app.data.insert('users', users)

@when('we post to "{url}"')
def step_impl(context, url):
    data = '{"data": %s}' % context.text
    context.response = context.client.post(url, data=data, headers=context.headers, follow_redirects=True)

@when('we get "{url}"')
def step_impl(context, url):
    context.response = context.client.get(url, follow_redirects=True)

@when('we delete "{url}"')
def step_impl(context, url):
    res = get_res(url, context)
    headers = [('If-Match', res['etag'])]
    context.response = context.client.delete(get_self_href(res), headers=headers, follow_redirects=True)

@when('we patch "{url}"')
def step_impl(context, url):
    res = get_res(url, context)
    headers = [('If-Match', res['etag'])]
    headers += context.headers
    data = '{"data": %s}' % context.text
    context.response = context.client.patch(get_self_href(res), data=data, headers=headers, follow_redirects=True)

@then('we get new resource')
def step_impl(context):
    data = json.loads(context.response.get_data())
    assert data['data']['status'] == 'OK', data['data']
    assert data['data']['_links']['self'], data['data']

@then('we get list with {total_count} items')
def step_impl(context, total_count):
    response_list = json.loads(context.response.get_data())
    assert len(response_list['_items']) == int(total_count), response_list

@then('we get no "{field}"')
def step_impl(context, field):
    response_data = json.loads(context.response.get_data())
    assert field not in response_data['data'], response_data

@then('we get existing resource')
def step_impl(context):
    resp = json.loads(context.response.get_data())
    assert context.response.status_code == 200, context.response.status_code

@then('we get OK response')
def step_impl(context):
    assert context.response.status_code == 200, context.response.get_data()

@then('we get updated response')
def step_impl(context):
    assert context.response.status_code == 200, context.response.status_code
