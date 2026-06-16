"""Raw email header fixtures for unit tests."""

# RFC 2047-encoded display name
RFC2047_FROM = "=?utf-8?b?TGlua2VkSW4=?= <messages-noreply@linkedin.com>"

# Plain From header
PLAIN_FROM = "GitHub <notifications@github.com>"

# From with angle brackets only (no display name)
BARE_FROM = "<noreply@stripe.com>"

# Unicode display name (not RFC 2047-encoded — raw UTF-8)
UNICODE_FROM = '"Björn Müller" <bjorn@example.de>'

# List-Unsubscribe with both mailto and https (RFC 8058 one-click)
ONE_CLICK_UNSUB = "<https://mail.example.com/u/abc?token=xyz>, <mailto:unsub@example.com?subject=unsub>"
ONE_CLICK_POST = "List-Unsubscribe=One-Click"

# List-Unsubscribe with https link only (no -Post → "link" capability)
LINK_ONLY_UNSUB = "<https://newsletter.example.com/unsubscribe/abc123>"

# List-Unsubscribe with mailto only
MAILTO_ONLY_UNSUB = "<mailto:list-unsubscribe@example.com?subject=Unsubscribe&body=Please+remove+me>"

# No List-Unsubscribe header
NO_UNSUB = None

# Encoded subject
ENCODED_SUBJECT = "=?UTF-8?Q?Your_Weekly_Digest_=E2=80=94_June_2026?="

# Raw Gmail API message payload (metadata format)
GMAIL_METADATA_MSG = {
    "id": "18f123abc",
    "threadId": "18f123abc",
    "payload": {
        "headers": [
            {"name": "From", "value": "Acme Marketing <promo@acme.com>"},
            {"name": "Subject", "value": "=?UTF-8?Q?Summer_Sale_=E2=80=94_50=25_off?="},
            {"name": "Date", "value": "Mon, 10 Jun 2026 09:00:00 +0000"},
            {"name": "List-Unsubscribe", "value": "<https://acme.com/unsub/tok>, <mailto:unsub@acme.com>"},
            {"name": "List-Unsubscribe-Post", "value": "List-Unsubscribe=One-Click"},
        ]
    },
}

GMAIL_NO_UNSUB_MSG = {
    "id": "18g456def",
    "threadId": "18g456def",
    "payload": {
        "headers": [
            {"name": "From", "value": "billing@aws.amazon.com"},
            {"name": "Subject", "value": "Your AWS invoice for June 2026"},
            {"name": "Date", "value": "Sat, 01 Jun 2026 00:00:00 +0000"},
        ]
    },
}
