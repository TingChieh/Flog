from app.email import send_email


def test_send_email_passes_extra_headers(application, outbox):
    with application.app_context():
        send_email('subject', 'noreply@example.com', ['reader@example.com'],
                   'text', '<p>html</p>',
                   headers={'List-Unsubscribe': '<https://example.com/u>'},
                   sync=True)
    assert outbox[-1].extra_headers == {
        'List-Unsubscribe': '<https://example.com/u>'}


def test_send_email_without_headers_still_works(application, outbox):
    with application.app_context():
        send_email('subject', 'noreply@example.com', ['reader@example.com'],
                   'text', '<p>html</p>', sync=True)
    assert outbox[-1].subject == 'subject'
