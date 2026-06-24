"""
Twilio WhatsApp Crisis Alert Service
Sends automated voice messages via WhatsApp when crisis is detected
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Iterable

# Twilio imports
try:
    from twilio.rest import Client
    from twilio.twiml.voice_response import VoiceResponse
    from twilio.twiml.messaging_response import MessagingResponse
except ImportError:
    print(" Twilio not installed. Install with: pip install twilio")
    Client = None


logger = logging.getLogger("sentimind.twilio")


class TwilioWhatsAppCrisisService:
    """
    Service to send automated WhatsApp voice messages when crisis detected
    """

    def __init__(self):
        """Initialize Twilio client with credentials from environment (with fallback)"""
        # Try primary credentials first
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        _using_fallback = False

        # Fallback to secondary credentials if primary not available
        if not self.account_sid or not self.auth_token:
            print(" [TWILIO] Primary credentials not found, trying fallback...")
            self.account_sid = os.getenv("TWILIO_ACCOUNT_SID_2")
            self.auth_token = os.getenv("TWILIO_AUTH_TOKEN_2")
            if self.account_sid and self.auth_token:
                print(" [TWILIO] Using fallback credentials (TWILIO_ACCOUNT_SID_2)")
                _using_fallback = True

        self.from_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "")  # whatsapp:+14155238886
        self.crisis_recipient = os.getenv("TWILIO_CRISIS_WHATSAPP_RECIPIENT", "")  # whatsapp:+923354815156
        self.sandbox_join_codes = [
            code.strip()
            for code in os.getenv(
                "TWILIO_WHATSAPP_JOIN_CODES",
                "join horse-few,join on-theory",
            ).split(",")
            if code.strip()
        ]

        # For SMS fallback: use account-matched phone numbers so from/account don't mismatch
        # When using account_2 credentials, prefer TWILIO_PHONE_NUMBER_2 if set
        if _using_fallback and os.getenv("TWILIO_PHONE_NUMBER_2"):
            self.sms_from = os.getenv("TWILIO_PHONE_NUMBER_2", "")
        else:
            self.sms_from = os.getenv("TWILIO_PHONE_NUMBER", "")  # +12183574322
        self.sms_crisis_recipient = os.getenv(
            "TWILIO_CRISIS_SMS_RECIPIENT",
            self.crisis_recipient.replace("whatsapp:", "")  # derive from WhatsApp number
        )

        if not all([self.account_sid, self.auth_token]):
            print(" [TWILIO] Credentials not configured in .env")
            print("   TWILIO_ACCOUNT_SID:", "set" if self.account_sid else " MISSING")
            print("   TWILIO_AUTH_TOKEN:", "set" if self.auth_token else " MISSING")
            print("   TWILIO_WHATSAPP_NUMBER:", "set" if self.from_number else " MISSING")
            print("   TWILIO_CRISIS_WHATSAPP_RECIPIENT:", "set" if self.crisis_recipient else " MISSING")
            print("    Try setting TWILIO_ACCOUNT_SID_2 and TWILIO_AUTH_TOKEN_2 for fallback")
            self.client = None
        else:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                cred_type = "fallback (2)" if _using_fallback else "primary"
                print(" [TWILIO] WhatsApp Crisis Service initialized successfully")
                print(f"   Credentials: {cred_type}")
                print(f"   WhatsApp from: {self.from_number}")
                print(f"   WhatsApp to:   {self.crisis_recipient}")
                print(f"   SMS fallback:  {self.sms_from}  ->  {self.sms_crisis_recipient}")
                print(f"   Sandbox joins: {', '.join(self.sandbox_join_codes) or 'none'}")
            except Exception as e:
                print(f" [TWILIO] Error initializing Twilio client: {e}")
                self.client = None

    @staticmethod
    def _whatsapp_to(phone: str) -> str:
        clean = str(phone or "").strip()
        return clean if clean.startswith("whatsapp:") else f"whatsapp:{clean}"

    @staticmethod
    def _sms_to(phone: str) -> str:
        return str(phone or "").replace("whatsapp:", "").strip()

    @staticmethod
    def _log_outbound_payload(
        *,
        label: str,
        channel: str,
        from_number: str,
        to_number: str,
        user_id: str,
        crisis_level: str,
        body: str,
    ) -> None:
        """
        Log the exact emergency message payload before Twilio send.

        These logs intentionally include the full alert body and recipient so
        local testing can verify exactly what emergency contacts receive.
        """
        text = (
            "\n[TWILIO-OUTBOUND] ===== EMERGENCY MESSAGE PREVIEW =====\n"
            f"[TWILIO-OUTBOUND] Alert type: {label}\n"
            f"[TWILIO-OUTBOUND] Channel:    {channel}\n"
            f"[TWILIO-OUTBOUND] From:       {from_number or 'not configured'}\n"
            f"[TWILIO-OUTBOUND] To:         {to_number or 'not configured'}\n"
            f"[TWILIO-OUTBOUND] User ID:    {user_id}\n"
            f"[TWILIO-OUTBOUND] Level:      {str(crisis_level or '').upper()}\n"
            "[TWILIO-OUTBOUND] Body start\n"
            f"{body}\n"
            "[TWILIO-OUTBOUND] Body end\n"
            "[TWILIO-OUTBOUND] ======================================\n"
        )
        print(text)
        logger.info(text)

    def build_sandbox_join_instruction(self) -> str:
        sandbox_number = self.from_number.replace("whatsapp:", "") or "+14155238886"
        # Build a wa.me deep-link for the first join code so the recipient can tap to open WhatsApp directly
        first_code = self.sandbox_join_codes[0] if self.sandbox_join_codes else "join horse-few"
        wa_link = f"https://wa.me/{sandbox_number.lstrip('+').replace(' ', '')}?text={first_code.replace(' ', '%20')}"
        steps = "\n".join(
            f"  Step {i+1}: Send \"{code}\" to {sandbox_number} on WhatsApp"
            for i, code in enumerate(self.sandbox_join_codes)
        )
        return (
            "ACTION REQUIRED — SentiMind Crisis Alert Setup\n\n"
            "You have been added as an emergency contact for a SentiMind mental-health user.\n"
            "To receive WhatsApp crisis alerts you MUST first join the SentiMind sandbox:\n\n"
            f"{steps}\n\n"
            f"Quick link (tap to open WhatsApp): {wa_link}\n\n"
            "Once you send the join phrase, crisis alerts (including live GPS location) "
            "will be delivered directly to your WhatsApp.\n"
            "You only need to do this once."
        )

    def send_sandbox_join_instruction(
        self,
        phone: str,
        *,
        name: str = "Emergency contact",
        prefer_whatsapp: bool = True,
    ) -> Dict[str, Any]:
        """
        Send Twilio Sandbox opt-in instructions to a crisis contact.

        Twilio Sandbox requires the recipient to send the join phrase to the
        sandbox number. This helper sends the instruction via SMS and also tries
        WhatsApp when possible, but it does not mark the recipient opted in.
        """
        if not self.client:
            return {"success": False, "error": "Twilio client not initialized"}

        body = self.build_sandbox_join_instruction()
        sms_to = self._sms_to(phone)
        whatsapp_to = self._whatsapp_to(phone)
        results: list[dict[str, Any]] = []

        def _record(channel: str, success: bool, message_sid: str | None = None, error: str | None = None):
            results.append({
                "channel": channel,
                "success": success,
                "message_sid": message_sid,
                "error": error,
            })

        whatsapp_succeeded = False
        if prefer_whatsapp and self.from_number:
            try:
                msg = self.client.messages.create(
                    from_=self.from_number,
                    to=whatsapp_to,
                    body=body,
                )
                _record("whatsapp", True, getattr(msg, "sid", None))
                whatsapp_succeeded = True
            except Exception as exc:
                _record("whatsapp", False, error=str(exc)[:300])

        always_send_sms = os.getenv("TWILIO_ALWAYS_SEND_JOIN_SMS", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if self.sms_from and sms_to and (always_send_sms or not whatsapp_succeeded):
            try:
                msg = self.client.messages.create(
                    from_=self.sms_from,
                    to=sms_to,
                    body=body,
                )
                _record("sms", True, getattr(msg, "sid", None))
            except Exception as exc:
                _record("sms", False, error=str(exc)[:300])

        successful = [item for item in results if item.get("success")]
        print(
            f"[TWILIO-BOOTSTRAP] Sandbox join instructions for {name} "
            f"({sms_to}): {len(successful)}/{len(results)} delivered"
        )
        return {
            "success": bool(successful),
            "phone": sms_to,
            "name": name,
            "join_codes": self.sandbox_join_codes,
            "results": results,
        }

    def send_sandbox_join_instructions(
        self,
        contacts: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        sent: list[dict[str, Any]] = []
        seen: set[str] = set()
        for contact in contacts:
            phone = self._sms_to(str(contact.get("phone") or ""))
            if not phone or phone in seen:
                continue
            seen.add(phone)
            sent.append(
                self.send_sandbox_join_instruction(
                    phone,
                    name=str(contact.get("name") or "Emergency contact"),
                    prefer_whatsapp=str(contact.get("channel") or "").lower() == "whatsapp",
                )
            )
        return {
            "success": any(item.get("success") for item in sent),
            "count": len(sent),
            "sent": sent,
        }


    def send_crisis_alert_voice_message(
        self,
        user_id: str,
        crisis_level: str,
        user_details: Optional[Dict[str, Any]] = None,
        recipient: Optional[str] = None,
        sms_recipient: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send automated voice message via WhatsApp when crisis detected

        Args:
            user_id: The user ID who triggered the crisis alert
            crisis_level: "high" or "medium"
            user_details: Optional details about the user and situation

        Returns:
            Dictionary with message SID and status
        """
        if not self.client:
            error_msg = "Twilio client not initialized - check credentials in .env"
            print(f" [TWILIO-WHATSAPP] {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "message_sid": None,
            }

        try:
            target_whatsapp = recipient or self.crisis_recipient
            target_sms = sms_recipient or (target_whatsapp or "").replace("whatsapp:", "") or self.sms_crisis_recipient

            if target_whatsapp and not target_whatsapp.startswith("whatsapp:"):
                target_whatsapp = f"whatsapp:{target_whatsapp}"

            # Validate recipient is configured
            if not target_whatsapp and not target_sms:
                error_msg = "No WhatsApp or SMS crisis recipient configured"
                print(f" [TWILIO-WHATSAPP] {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "message_sid": None,
                }

            if not self.from_number:
                error_msg = "TWILIO_WHATSAPP_NUMBER not configured in .env"
                print(f" [TWILIO-WHATSAPP] {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "message_sid": None,
                }
            
            #  Build message body 
            # Detect whether voice was part of the trigger
            source_tag = user_details.get("source", "Text Message") if user_details else "Text Message"
            voice_section = ""
            if user_details and "voice_emotion" in user_details:
                voice_section = (
                    f"\n VOICE ACOUSTIC SIGNALS:\n"
                    f"  Voice emotion:       {user_details.get('voice_emotion', 'N/A')}\n"
                    f"  Distress index:      {user_details.get('distress_index', 'N/A')}\n"
                    f"  Pause density:       {user_details.get('pause_density', 'N/A')}\n"
                    f"  Voice/text conflict: {user_details.get('voice_text_conflict', 'N/A')}\n"
                )

            if crisis_level == "high":
                message_body = (
                    " URGENT CRISIS ALERT \n\n"
                    "A user in our SentiMind mental health app is showing signs of IMMEDIATE self-harm risk.\n\n"
                    "CRISIS LEVEL: HIGH \n"
                    "USER:          {user_label}\n"
                    "DETECTED VIA:  {source}\n"
                    "TIME:          {timestamp}\n\n"
                    " EMOTIONAL ANALYSIS:\n"
                    "{details}\n"
                    "{voice_section}"
                    "\nPlease respond IMMEDIATELY. This is an automated alert from SentiMind Mental Health Support.\n"
                    "Reply to acknowledge receipt."
                )
            else:
                message_body = (
                    " MENTAL HEALTH CRISIS ALERT\n\n"
                    "A user in our SentiMind mental health app is showing signs of psychological distress with self-harm ideation.\n\n"
                    "CRISIS LEVEL: MEDIUM \n"
                    "USER:          {user_label}\n"
                    "DETECTED VIA:  {source}\n"
                    "TIME:          {timestamp}\n\n"
                    " EMOTIONAL ANALYSIS:\n"
                    "{details}\n"
                    "{voice_section}"
                    "\nPlease respond with assistance options. This is an automated alert from SentiMind Mental Health Support.\n"
                    "Reply to acknowledge receipt."
                )


            # Format message with user details - with proper encoding
            details_text = ""
            if user_details:
                try:
                    details_parts = []
                    for key, value in user_details.items():
                        # Safely encode each detail line
                        safe_value = str(value).encode('utf-8', errors='ignore').decode('utf-8')
                        details_parts.append(f"- {key}: {safe_value}")
                    details_text = "\n".join(details_parts)
                except Exception as e:
                    print(f"[TWILIO-WHATSAPP]  Error encoding user details: {e}")
                    details_text = "- [Details encoding error]\n"

            # Prefer the person's name; fall back to the user_id only if no name is known.
            user_label = (user_name or "").strip() or (
                str(user_details.get("user_name")).strip() if user_details and user_details.get("user_name") else ""
            ) or user_id
            final_message = message_body.format(
                user_label=user_label,
                source=source_tag,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                details=details_text or "N/A",
                voice_section=voice_section,
            )
            
            # Ensure final message is properly UTF-8 encoded
            try:
                final_message = final_message.encode('utf-8', errors='ignore').decode('utf-8')
            except Exception as e:
                print(f"[TWILIO-WHATSAPP]  Error encoding final message: {e}")
                final_message = final_message.encode('ascii', errors='ignore').decode('ascii')

            print(f"\n[TWILIO-WHATSAPP]  Sending crisis alert...")
            print(f"[TWILIO-WHATSAPP] From: {self.from_number}")
            print(f"[TWILIO-WHATSAPP] To: {target_whatsapp or target_sms}")
            print(f"[TWILIO-WHATSAPP] Level: {crisis_level.upper()}")
            print(f"[TWILIO-WHATSAPP] User ID: {user_id}")

            #  Try WhatsApp first, fall back to SMS automatically 
            import asyncio

            def _send_whatsapp():
                # Ensure message is UTF-8 safe before sending
                safe_body = final_message.encode('utf-8', errors='ignore').decode('utf-8')
                self._log_outbound_payload(
                    label="crisis-alert",
                    channel="whatsapp",
                    from_number=self.from_number,
                    to_number=target_whatsapp,
                    user_id=user_id,
                    crisis_level=crisis_level,
                    body=safe_body,
                )
                return self.client.messages.create(
                    from_=self.from_number,       # whatsapp:+12183574322
                    to=target_whatsapp,           # whatsapp:+923354815156
                    body=safe_body
                )

            def _send_sms():
                # Use plain E.164 phone numbers (no whatsapp: prefix) for SMS
                # Ensure message is UTF-8 safe before sending
                safe_body = final_message.encode('utf-8', errors='ignore').decode('utf-8')
                self._log_outbound_payload(
                    label="crisis-alert",
                    channel="sms",
                    from_number=self.sms_from,
                    to_number=target_sms,
                    user_id=user_id,
                    crisis_level=crisis_level,
                    body=safe_body,
                )
                return self.client.messages.create(
                    from_=self.sms_from,
                    to=target_sms,
                    body=safe_body
                )

            message = None
            channel_used = "whatsapp"

            try:
                # Attempt WhatsApp (requires WhatsApp channel enabled on Twilio)
                print(f"[TWILIO-WHATSAPP] Attempting WhatsApp channel...")
                message = _send_whatsapp()
                print(f"[TWILIO-WHATSAPP]  WhatsApp alert sent! SID: {message.sid}")
            except Exception as wa_err:
                print(f"[TWILIO-WHATSAPP]  WhatsApp failed ({wa_err.__class__.__name__}): {str(wa_err)[:120]}")
                print(f"[TWILIO-WHATSAPP]  Attempting SMS fallback...")
                try:
                    message = _send_sms()
                    channel_used = "sms"
                    print(f"[TWILIO-SMS]  SMS fallback sent! SID: {message.sid}")
                except Exception as sms_err:
                    print(f"[TWILIO-SMS]  SMS fallback also failed: {sms_err}")
                    raise sms_err

            return {
                "success": True,
                "message_sid": message.sid,
                "status": message.status,
                "channel": channel_used,
                "timestamp": datetime.now().isoformat(),
                "crisis_level": crisis_level,
                "recipient": target_whatsapp or target_sms,
            }

        except Exception as e:
            print(f"[TWILIO-WHATSAPP]  Crisis alert failed (all channels): {e}")
            import traceback
            print(f"[TWILIO-WHATSAPP] Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "message_sid": None,
                "timestamp": datetime.now().isoformat(),
                "crisis_level": crisis_level,
            }

    def send_location_alert(
        self,
        user_id: str,
        latitude: float,
        longitude: float,
        accuracy: Optional[float] = None,
        crisis_level: str = "high",
        city: Optional[str] = None,
        region: Optional[str] = None,
        country: Optional[str] = None,
        method: str = "GPS",
        recipient: Optional[str] = None,
        sms_recipient: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a WhatsApp alert with GPS or IP-based location when crisis is detected.

        Builds a clickable Google Maps link and sends it to the configured
        crisis recipient (TWILIO_CRISIS_WHATSAPP_RECIPIENT).

        Args:
            user_id:      The user ID who triggered the crisis alert
            latitude:     Latitude (from GPS or IP geolocation)
            longitude:    Longitude (from GPS or IP geolocation)
            accuracy:     Optional accuracy radius (e.g., "500 metres" for IP, "20 metres" for GPS)
            crisis_level: "high" or "medium"
            city:         Optional city name (for IP-based)
            region:       Optional region/state (for IP-based)
            country:      Optional country (for IP-based)
            method:       "GPS", "IP-based", etc. to indicate location method

        Returns:
            Dictionary with success status, message_sid, and channel used
        """
        if not self.client:
            error_msg = "Twilio client not initialized - check credentials in .env"
            print(f"[TWILIO-LOC] \u274c {error_msg}")
            return {"success": False, "error": error_msg, "message_sid": None}

        target_whatsapp = recipient
        target_sms = sms_recipient
        if not target_whatsapp and not target_sms:
            target_whatsapp = self.crisis_recipient
            target_sms = self.sms_crisis_recipient or (target_whatsapp or "").replace("whatsapp:", "")
        elif target_whatsapp and not target_sms:
            target_sms = target_whatsapp.replace("whatsapp:", "")

        if not target_whatsapp and not target_sms:
            error_msg = "No crisis alert recipient configured or saved"
            print(f"[TWILIO-LOC] \u274c {error_msg}")
            return {"success": False, "error": error_msg, "message_sid": None}

        try:
            maps_link = f"https://maps.google.com/?q={latitude},{longitude}"
            
            # Format accuracy text based on type
            if isinstance(accuracy, str):
                accuracy_text = f" Accuracy: {accuracy}\n"
            elif accuracy:
                accuracy_text = f" Accuracy: {accuracy:.0f} metres\n"
            else:
                accuracy_text = ""
            
            # Format location details with proper encoding
            location_details = ""
            if city or region or country:
                try:
                    # Safely encode location parts to avoid UTF-8 issues
                    location_parts = []
                    for p in [city, region, country]:
                        if p and p != "Unknown":
                            # Encode and decode to ensure valid UTF-8
                            safe_p = str(p).encode('utf-8', errors='ignore').decode('utf-8')
                            location_parts.append(safe_p)
                    if location_parts:
                        location_details = f" LOCATION: {', '.join(location_parts)}\n"
                except Exception as e:
                    print(f"[TWILIO-LOC]  Error encoding location: {e}")
                    location_details = " LOCATION: Location data unavailable\n"
            
            level_icon = "" if crisis_level == "high" else ""
            level_label = "HIGH " if crisis_level == "high" else "MEDIUM "
            
            # Format method display
            method_display = method
            if method == "GPS":
                method_display = " GPS (Precise Location - User Allowed)"
            elif method.startswith("IP-based"):
                method_display = "IP-based fallback (approximate)"
            
            # Add emphasis for GPS-based alerts
            gps_notice = ""
            if method == "GPS":
                gps_notice = " THIS IS A PRECISE GPS-BASED LOCATION (5-20 meters accuracy)\n\n"
            elif method.startswith("IP-based"):
                gps_notice = "This is an approximate IP-based fallback location. GPS was denied or unavailable.\n\n"

            message_body = (
                f"{level_icon} SentiMind CRISIS ALERT  LOCATION REPORT\n\n"
                f"{gps_notice}"
                f"A user has been detected in psychological distress.\n\n"
                f" CRISIS LEVEL: {level_label}\n"
                f" USER ID:       {user_id}\n"
                f" TIME:          {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f" METHOD:        {method_display}\n\n"
                f"{location_details}"
                f" COORDINATES:\n"
                f"  Latitude:  {latitude:.6f}\n"
                f"  Longitude: {longitude:.6f}\n"
                f"{accuracy_text}"
                f"\n OPEN IN MAPS:\n{maps_link}\n\n"
                f"This is an automated crisis alert from SentiMind Mental Health Support.\n"
                f"Please check on this user immediately."
            )
            
            # Ensure message body is properly encoded as UTF-8
            try:
                message_body = message_body.encode('utf-8', errors='ignore').decode('utf-8')
            except Exception as e:
                print(f"[TWILIO-LOC]  Error encoding message body: {e}")
                # Fallback: remove problematic characters
                message_body = message_body.encode('ascii', errors='ignore').decode('ascii')

            print(f"\n[TWILIO-LOC]  Sending location alert to WhatsApp crisis center...")
            print(f"[TWILIO-LOC]   User:     {user_id}")
            print(f"[TWILIO-LOC]   Level:    {crisis_level.upper()}")
            print(f"[TWILIO-LOC]   Location: {location_details.strip() if location_details else 'GPS Coordinates Only'}")
            print(f"[TWILIO-LOC]   LatLng:   {latitude:.5f}, {longitude:.5f}")
            print(f"[TWILIO-LOC]   Accuracy: {accuracy}")
            print(f"[TWILIO-LOC]   Method:   {method}")
            
            # Highlight GPS vs IP-based
            if method == "GPS":
                print(f"[TWILIO-LOC]  USING PRECISE GPS LOCATION (5-20m accuracy)")
            elif method.startswith("IP-based"):
                print(f"[TWILIO-LOC]   USING APPROXIMATE IP-BASED FALLBACK")
            
            print(f"[TWILIO-LOC]   Maps:     {maps_link}")
            print(f"[TWILIO-LOC]   To:       {target_whatsapp or target_sms}")

            message = None
            channel_used = "whatsapp"
            
            # Ensure message body is UTF-8 safe
            try:
                safe_message_body = message_body.encode('utf-8', errors='ignore').decode('utf-8')
            except Exception as e:
                print(f"[TWILIO-LOC]  Error encoding message: {e}")
                safe_message_body = message_body.encode('ascii', errors='ignore').decode('ascii')

            try:
                if not target_whatsapp or not self.from_number:
                    raise ValueError("WhatsApp sender or recipient not configured")
                self._log_outbound_payload(
                    label="location-alert",
                    channel="whatsapp",
                    from_number=self.from_number,
                    to_number=target_whatsapp,
                    user_id=user_id,
                    crisis_level=crisis_level,
                    body=safe_message_body,
                )
                message = self.client.messages.create(
                    from_=self.from_number,
                    to=target_whatsapp,
                    body=safe_message_body
                )
                print(f"[TWILIO-LOC]  WhatsApp location alert sent! SID: {message.sid}")
            except Exception as wa_err:
                print(f"[TWILIO-LOC]  WhatsApp failed ({wa_err.__class__.__name__}): {str(wa_err)[:120]}")
                print(f"[TWILIO-LOC]  Falling back to SMS...")
                try:
                    if not target_sms or not self.sms_from:
                        raise ValueError("SMS sender or recipient not configured")
                    self._log_outbound_payload(
                        label="location-alert",
                        channel="sms",
                        from_number=self.sms_from,
                        to_number=target_sms,
                        user_id=user_id,
                        crisis_level=crisis_level,
                        body=safe_message_body,
                    )
                    message = self.client.messages.create(
                        from_=self.sms_from,
                        to=target_sms,
                        body=safe_message_body
                    )
                    channel_used = "sms"
                    print(f"[TWILIO-LOC]  SMS location alert sent! SID: {message.sid}")
                except Exception as sms_err:
                    print(f"[TWILIO-LOC]  SMS fallback failed: {sms_err}")
                    raise sms_err

            return {
                "success": True,
                "message_sid": str(message.sid) if hasattr(message, 'sid') else None,
                "status": str(message.status) if hasattr(message, 'status') else "sent",
                "channel": channel_used,
                "timestamp": datetime.now().isoformat(),
                "crisis_level": crisis_level,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "maps_link": str(maps_link),
                "recipient": str(target_whatsapp or target_sms),
            }

        except Exception as e:
            print(f"[TWILIO-LOC]  Location alert failed: {e}")
            import traceback
            print(f"[TWILIO-LOC] Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "message_sid": None,
                "timestamp": datetime.now().isoformat(),
            }


    def send_text_alert(
        self,
        message_text: str,
        recipient: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send plain text WhatsApp message

        Args:
            message_text: Text to send
            recipient: WhatsApp recipient (defaults to crisis recipient)

        Returns:
            Message status and SID
        """
        if not self.client:
            return {"success": False, "error": "Twilio not configured"}

        try:
            to_number = recipient or self.crisis_recipient

            message = self.client.messages.create(
                from_=self.from_number,
                to=to_number,
                body=message_text
            )

            return {
                "success": True,
                "message_sid": message.sid,
                "status": message.status,
            }

        except Exception as e:
            print(f"[TWILIO] Error: {e}")
            return {"success": False, "error": str(e)}

    def get_message_status(self, message_sid: str) -> Dict[str, Any]:
        """
        Get status of a sent message

        Args:
            message_sid: The Twilio message SID

        Returns:
            Current status of the message
        """
        if not self.client:
            return {"error": "Twilio not configured"}

        try:
            message = self.client.messages(message_sid).fetch()
            return {
                "message_sid": message.sid,
                "status": message.status,
                "to": message.to,
                "from": message.from_,
                "date_sent": str(message.date_sent),
            }
        except Exception as e:
            print(f"[TWILIO] Error fetching status: {e}")
            return {"error": str(e)}


# Singleton instance
_crisis_service = None


def get_crisis_whatsapp_service() -> TwilioWhatsAppCrisisService:
    """Get or create the Twilio crisis service singleton"""
    global _crisis_service
    if _crisis_service is None:
        _crisis_service = TwilioWhatsAppCrisisService()
    return _crisis_service
