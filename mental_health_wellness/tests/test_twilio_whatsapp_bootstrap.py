from mental_health_wellness.services.twilio_whatsapp_crisis import TwilioWhatsAppCrisisService


class _FakeMessage:
    sid = "SM_TEST"
    status = "queued"


class _FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeMessage()


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


def test_twilio_sandbox_join_instruction_includes_configured_codes(monkeypatch):
    monkeypatch.setenv("TWILIO_WHATSAPP_JOIN_CODES", "join horse-few,join on-theory")
    monkeypatch.setenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID_2", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN_2", raising=False)

    service = TwilioWhatsAppCrisisService()
    instruction = service.build_sandbox_join_instruction()

    assert "join horse-few" in instruction
    assert "join on-theory" in instruction
    assert "+14155238886" in instruction
    assert "WhatsApp crisis alerts" in instruction


def test_crisis_alert_logs_exact_outbound_whatsapp_payload(monkeypatch, capsys):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID_2", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN_2", raising=False)

    service = TwilioWhatsAppCrisisService()
    fake_client = _FakeClient()
    service.client = fake_client
    service.from_number = "whatsapp:+14155238886"
    service.sms_from = "+15550000000"
    service.crisis_recipient = "whatsapp:+923001234567"
    service.sms_crisis_recipient = "+923001234567"

    result = service.send_crisis_alert_voice_message(
        user_id="user_123",
        crisis_level="high",
        user_details={
            "source": "Voice + Text Message",
            "message_preview": "I have a knife and I'm going to kill",
        },
    )

    captured = capsys.readouterr().out
    assert result["success"] is True
    assert "[TWILIO-OUTBOUND] ===== EMERGENCY MESSAGE PREVIEW =====" in captured
    assert "[TWILIO-OUTBOUND] Channel:    whatsapp" in captured
    assert "[TWILIO-OUTBOUND] To:         whatsapp:+923001234567" in captured
    assert "URGENT CRISIS ALERT" in captured
    assert "I have a knife and I'm going to kill" in captured
    assert fake_client.messages.calls[0]["body"] in captured
