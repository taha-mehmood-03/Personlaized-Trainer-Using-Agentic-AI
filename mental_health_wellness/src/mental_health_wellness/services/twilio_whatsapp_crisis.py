"""
Twilio WhatsApp Crisis Alert Service
Sends automated voice messages via WhatsApp when crisis is detected
"""

import os
import json
from datetime import datetime
from typing import Optional, Dict, Any

# Twilio imports
try:
    from twilio.rest import Client
    from twilio.twiml.voice_response import VoiceResponse
    from twilio.twiml.messaging_response import MessagingResponse
except ImportError:
    print(" Twilio not installed. Install with: pip install twilio")
    Client = None


class TwilioWhatsAppCrisisService:
    """
    Service to send automated WhatsApp voice messages when crisis detected
    """

    def __init__(self):
        """Initialize Twilio client with credentials from environment (with fallback)"""
        # Try primary credentials first
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        
        # Fallback to secondary credentials if primary not available
        if not self.account_sid or not self.auth_token:
            print(" [TWILIO] Primary credentials not found, trying fallback...")
            self.account_sid = os.getenv("TWILIO_ACCOUNT_SID_2")
            self.auth_token = os.getenv("TWILIO_AUTH_TOKEN_2")
            if self.account_sid and self.auth_token:
                print(" [TWILIO] Using fallback credentials (TWILIO_ACCOUNT_SID_2)")
        
        self.from_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "")  # whatsapp:+12183574322
        self.crisis_recipient = os.getenv("TWILIO_CRISIS_WHATSAPP_RECIPIENT", "")  # whatsapp:+923354815156

        # For SMS fallback: plain E.164 numbers (no whatsapp: prefix)
        self.sms_from = os.getenv("TWILIO_PHONE_NUMBER", "")  # +12183574322
        self.sms_crisis_recipient = os.getenv(
            "TWILIO_CRISIS_SMS_RECIPIENT",
            self.crisis_recipient.replace("whatsapp:", "")  # derive from WhatsApp number
        )

        if not all([self.account_sid, self.auth_token]):
            print(" [TWILIO] Credentials not configured in .env")
            print("   TWILIO_ACCOUNT_SID:", "" if self.account_sid else " MISSING")
            print("   TWILIO_AUTH_TOKEN:", "" if self.auth_token else " MISSING")
            print("   TWILIO_WHATSAPP_NUMBER:", "" if self.from_number else " MISSING")
            print("   TWILIO_CRISIS_WHATSAPP_RECIPIENT:", "" if self.crisis_recipient else " MISSING")
            print("    Try setting TWILIO_ACCOUNT_SID_2 and TWILIO_AUTH_TOKEN_2 for fallback")
            self.client = None
        else:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                cred_type = "fallback (2)" if os.getenv("TWILIO_ACCOUNT_SID") is None else "primary"
                print(" [TWILIO] WhatsApp Crisis Service initialized successfully")
                print(f"   Credentials: {cred_type}")
                print(f"   WhatsApp from: {self.from_number}")
                print(f"   WhatsApp to:   {self.crisis_recipient}")
                print(f"   SMS fallback:  {self.sms_from}  {self.sms_crisis_recipient}")
            except Exception as e:
                print(f" [TWILIO] Error initializing Twilio client: {e}")
                self.client = None


    def send_crisis_alert_voice_message(
        self,
        user_id: str,
        crisis_level: str,
        user_details: Optional[Dict[str, Any]] = None
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
            # Validate recipient is configured
            if not self.crisis_recipient:
                error_msg = "TWILIO_CRISIS_WHATSAPP_RECIPIENT not configured in .env"
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
                    "USER ID:       {user_id}\n"
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
                    "USER ID:       {user_id}\n"
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

            final_message = message_body.format(
                user_id=user_id,
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
            print(f"[TWILIO-WHATSAPP] To: {self.crisis_recipient}")
            print(f"[TWILIO-WHATSAPP] Level: {crisis_level.upper()}")
            print(f"[TWILIO-WHATSAPP] User ID: {user_id}")

            #  Try WhatsApp first, fall back to SMS automatically 
            import asyncio

            def _send_whatsapp():
                # Ensure message is UTF-8 safe before sending
                safe_body = final_message.encode('utf-8', errors='ignore').decode('utf-8')
                return self.client.messages.create(
                    from_=self.from_number,       # whatsapp:+12183574322
                    to=self.crisis_recipient,     # whatsapp:+923354815156
                    body=safe_body
                )

            def _send_sms():
                # Use plain E.164 phone numbers (no whatsapp: prefix) for SMS
                # Ensure message is UTF-8 safe before sending
                safe_body = final_message.encode('utf-8', errors='ignore').decode('utf-8')
                return self.client.messages.create(
                    from_=self.sms_from,
                    to=self.sms_crisis_recipient,
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
                "recipient": self.crisis_recipient,
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
        method: str = "GPS"
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

        if not self.crisis_recipient:
            error_msg = "TWILIO_CRISIS_WHATSAPP_RECIPIENT not configured in .env"
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
            elif method == "IP-based (automatic, no permission needed)":
                method_display = " IP-Based (Fallback - User Denied GPS)"
            
            # Add emphasis for GPS-based alerts
            gps_notice = ""
            if method == "GPS":
                gps_notice = " THIS IS A PRECISE GPS-BASED LOCATION (5-20 meters accuracy)\n\n"
            elif method == "IP-based (automatic, no permission needed)":
                gps_notice = " This is an IP-based fallback location (500 km accuracy). GPS was denied/unavailable.\n\n"

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
            elif method == "IP-based (automatic, no permission needed)":
                print(f"[TWILIO-LOC]   USING IP-BASED FALLBACK (500km accuracy - user denied GPS)")
            
            print(f"[TWILIO-LOC]   Maps:     {maps_link}")
            print(f"[TWILIO-LOC]   To:       {self.crisis_recipient}")

            message = None
            channel_used = "whatsapp"
            
            # Ensure message body is UTF-8 safe
            try:
                safe_message_body = message_body.encode('utf-8', errors='ignore').decode('utf-8')
            except Exception as e:
                print(f"[TWILIO-LOC]  Error encoding message: {e}")
                safe_message_body = message_body.encode('ascii', errors='ignore').decode('ascii')

            try:
                message = self.client.messages.create(
                    from_=self.from_number,
                    to=self.crisis_recipient,
                    body=safe_message_body
                )
                print(f"[TWILIO-LOC]  WhatsApp location alert sent! SID: {message.sid}")
            except Exception as wa_err:
                print(f"[TWILIO-LOC]  WhatsApp failed ({wa_err.__class__.__name__}): {str(wa_err)[:120]}")
                print(f"[TWILIO-LOC]  Falling back to SMS...")
                try:
                    message = self.client.messages.create(
                        from_=self.sms_from,
                        to=self.sms_crisis_recipient,
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
                "recipient": str(self.crisis_recipient),
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
