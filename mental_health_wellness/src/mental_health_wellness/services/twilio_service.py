"""
Twilio Service - Handle emergency calls and SMS
Supports direct calling to crisis hotlines for users in emergency situations
Specialized for Pakistan crisis center integration (Tele-Tabeeb 1123)
"""

import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum

# Try to import Twilio, but handle gracefully if not installed
try:
    from twilio.rest import Client
    from twilio.twiml.voice_response import VoiceResponse
    TWILIO_AVAILABLE = True
except ImportError:
    print("[TWILIO] ⚠️ Twilio package not installed. Install with: pip install twilio")
    Client = None
    VoiceResponse = None
    TWILIO_AVAILABLE = False


class CrisisLevel(str, Enum):
    """Crisis severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TwilioService:
    """Service for initiating emergency calls via Twilio"""
    
    def __init__(self):
        """Initialize Twilio client with credentials from environment"""
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.phone_number = os.getenv("TWILIO_PHONE_NUMBER", "")
        self.whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "")
        
        # Pakistan crisis center
        self.pakistan_crisis_center = os.getenv(
            "PAKISTAN_CRISIS_CENTER_NUMBER", 
            "+923001123123"
        )
        self.pakistan_crisis_center_name = os.getenv(
            "PAKISTAN_CRISIS_CENTER_NAME",
            "Tele-Tabeeb 1123"
        )
        self.backend_webhook_url = os.getenv(
            "BACKEND_WEBHOOK_URL",
            "http://localhost:8000"
        )
        
        if not TWILIO_AVAILABLE:
            print("[TWILIO] ⚠️ Warning: Twilio is not installed. Please install with: pip install twilio")
            self.client = None
            return
        
        if not all([self.account_sid, self.auth_token, self.phone_number]):
            print("[TWILIO] ⚠️ Warning: Twilio credentials not configured")
            self.client = None
        else:
            self.client = Client(self.account_sid, self.auth_token)
            print(f"[TWILIO] ✅ Initialized with phone: {self.phone_number}")
            print(f"[TWILIO] 🇵🇰 Pakistan Crisis Center: {self.pakistan_crisis_center_name}")
    
    async def call_pakistan_crisis_center(
        self,
        user_id: str,
        user_name: str,
        crisis_level: CrisisLevel,
        message_excerpt: str,
        user_phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initiate emergency voice call to Pakistan's Tele-Tabeeb 1123
        
        Args:
            user_id: User ID from database
            user_name: User's name or display name
            crisis_level: Severity level (low, medium, high, critical)
            message_excerpt: The message that triggered crisis detection
            user_phone: Optional user phone number for callback
            
        Returns:
            Dict with call status, call SID, and metadata
        """
        if not self.client:
            return {
                "success": False,
                "reason": "twilio_not_configured",
                "status": "failed",
            }

        try:
            print(f"\n{'='*60}")
            print(f"[TWILIO-CALL] 🚨 INITIATING EMERGENCY CALL TO PAKISTAN CRISIS CENTER")
            print(f"[TWILIO-CALL] User ID: {user_id}")
            print(f"[TWILIO-CALL] User Name: {user_name}")
            print(f"[TWILIO-CALL] Crisis Level: {crisis_level}")
            print(f"[TWILIO-CALL] Target: {self.pakistan_crisis_center_name}")
            print(f"[TWILIO-CALL] Number: {self.pakistan_crisis_center}")
            print(f"{'='*60}")

            # Build TwiML for the call
            response = VoiceResponse()
            
            # Welcome message
            response.say(
                f"Emergency alert from SentiMind Mental Health Application. "
                f"A user is experiencing a crisis situation and requires immediate assistance.",
                voice="alice"
            )
            
            # Crisis details
            response.say(
                f"Crisis Level: {crisis_level}. "
                f"User Name: {user_name}. "
                f"User ID: {user_id}.",
                voice="alice"
            )
            
            # User's message excerpt
            response.say(
                f"User reported: {message_excerpt[:80]}",
                voice="alice"
            )
            
            # Request acknowledgment
            response.gather(
                num_digits=1,
                action=f"{self.backend_webhook_url}/api/crisis/twilio/response",
                method="POST",
                timeout=30
            ).say(
                "Press 1 to acknowledge this emergency alert and review the incident, "
                "or press 2 to be connected with a specialist.",
                voice="alice"
            )

            # Make the call using run_in_executor since Twilio client is sync
            loop = asyncio.get_event_loop()
            call = await loop.run_in_executor(
                None,
                lambda: self.client.calls.create(
                    to=self.pakistan_crisis_center,
                    from_=self.phone_number,
                    twiml=str(response),
                    status_callback=f"{self.backend_webhook_url}/api/crisis/twilio/status",
                    status_callback_method="POST",
                    record=True,
                )
            )

            print(f"[TWILIO-CALL] ✅ Call initiated successfully")
            print(f"[TWILIO-CALL] Call SID: {call.sid}")
            print(f"[TWILIO-CALL] Status: {call.status}")
            print(f"[TWILIO-CALL] To: {call.to}")
            print(f"{'='*60}\n")

            return {
                "success": True,
                "status": "call_initiated",
                "call_sid": call.sid,
                "crisis_center": self.pakistan_crisis_center_name,
                "crisis_center_number": self.pakistan_crisis_center,
                "crisis_level": crisis_level,
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": user_id,
                "user_name": user_name,
            }

        except Exception as e:
            print(f"[TWILIO-CALL] ❌ Error initiating emergency call: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "status": "call_failed",
                "error": str(e),
                "crisis_level": crisis_level,
            }
    
    async def send_crisis_alert_sms(
        self,
        crisis_center_number: str,
        user_id: str,
        user_name: str,
        crisis_level: CrisisLevel,
        message_excerpt: str,
    ) -> Dict[str, Any]:
        """
        Send SMS alert to crisis center
        
        Args:
            crisis_center_number: Phone number to send SMS to
            user_id: User ID
            user_name: User's name
            crisis_level: Crisis severity
            message_excerpt: The triggering message
            
        Returns:
            Dict with SMS status
        """
        if not self.client:
            return {"success": False, "reason": "twilio_not_configured"}

        try:
            alert_text = (
                f"🚨 CRISIS ALERT from SentiMind:\n"
                f"User: {user_name} (ID: {user_id})\n"
                f"Level: {crisis_level.upper()}\n"
                f"Message: {message_excerpt[:50]}...\n"
                f"Time: {datetime.utcnow().strftime('%H:%M:%S UTC')}"
            )

            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    body=alert_text,
                    from_=self.phone_number,
                    to=crisis_center_number,
                )
            )

            print(f"[TWILIO-SMS] ✅ Alert SMS sent to {crisis_center_number}")
            print(f"[TWILIO-SMS] Message SID: {message.sid}")

            return {
                "success": True,
                "status": "sms_sent",
                "message_sid": message.sid,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            print(f"[TWILIO-SMS] ❌ Error sending SMS: {e}")
            return {"success": False, "error": str(e)}

    async def send_crisis_alert_whatsapp(
        self,
        crisis_center_number: str,
        user_id: str,
        user_name: str,
        crisis_level: CrisisLevel,
        message_excerpt: str,
    ) -> Dict[str, Any]:
        """
        Send WhatsApp alert to crisis center
        
        Args:
            crisis_center_number: WhatsApp number (with whatsapp: prefix)
            user_id: User ID
            user_name: User's name
            crisis_level: Crisis severity
            message_excerpt: The triggering message
            
        Returns:
            Dict with WhatsApp status
        """
        if not self.client:
            return {"success": False, "reason": "twilio_not_configured"}

        try:
            alert_text = (
                f"🚨 CRISIS ALERT from SentiMind:\n\n"
                f"👤 User: {user_name} (ID: {user_id})\n"
                f"🔴 Level: {crisis_level.upper()}\n"
                f"💬 Message: {message_excerpt[:50]}...\n"
                f"🕐 Time: {datetime.utcnow().strftime('%H:%M:%S UTC')}\n\n"
                f"Please review and respond immediately if possible."
            )

            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    body=alert_text,
                    from_=self.whatsapp_number,
                    to=crisis_center_number,
                )
            )

            print(f"[TWILIO-WHATSAPP] ✅ WhatsApp alert sent to {crisis_center_number}")
            print(f"[TWILIO-WHATSAPP] Message SID: {message.sid}")

            return {
                "success": True,
                "status": "whatsapp_sent",
                "message_sid": message.sid,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            print(f"[TWILIO-WHATSAPP] ❌ Error sending WhatsApp: {e}")
            return {"success": False, "error": str(e)}

    def initiate_crisis_call(
        self,
        user_phone: str,
        hotline_number: str,
        user_id: str = "unknown",
        country: str = "US"
    ) -> Dict[str, Any]:
        """
        Initiate a conference call between user and crisis hotline.
        
        Args:
            user_phone: User's phone number in E.164 format (+1234567890)
            hotline_number: Crisis hotline number to connect to
            user_id: User ID for logging
            country: Country code for context (US, PK, etc.)
            
        Returns:
            Dictionary with call status and details
        """
        if not self.client:
            return {
                "success": False,
                "error": "Twilio not configured",
                "message": "Direct calling is not available. Please dial the number directly."
            }
        
        try:
            print(f"[TWILIO] 📞 Initiating crisis call for user {user_id} to {hotline_number}")
            
            # Create TwiML for call flow
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="en">Connecting you to crisis support. Please stay on the line.</Say>
    <Dial timeout="30" record="record-from-answer">
        <Number>{hotline_number}</Number>
    </Dial>
</Response>"""
            
            # Make outbound call to user
            call = self.client.calls.create(
                to=user_phone,
                from_=self.phone_number,
                twiml=twiml,
                timeout=30,
                status_callback=os.getenv("TWILIO_STATUS_CALLBACK_URL", ""),
                status_callback_method="POST"
            )
            
            print(f"[TWILIO] ✅ Call initiated: {call.sid}")
            
            return {
                "success": True,
                "call_sid": call.sid,
                "message": f"Connecting you to crisis support in {country}. Please stay on the line.",
                "user_id": user_id,
                "country": country
            }
        
        except Exception as e:
            error_msg = str(e)
            print(f"[TWILIO] ❌ Error initiating call: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "message": "Unable to initiate direct call. Please dial the crisis hotline directly."
            }
    
    def send_crisis_sms(
        self,
        user_phone: str,
        message: str,
        user_id: str = "unknown"
    ) -> Dict[str, Any]:
        """
        Send SMS crisis resources to user's phone.
        
        Args:
            user_phone: User's phone number in E.164 format
            message: SMS content
            user_id: User ID for logging
            
        Returns:
            Dictionary with SMS status
        """
        if not self.client:
            return {
                "success": False,
                "error": "Twilio not configured",
                "message": "SMS not available"
            }
        
        try:
            print(f"[TWILIO] 📱 Sending crisis SMS to {user_phone}")
            
            sms = self.client.messages.create(
                body=message,
                from_=self.phone_number,
                to=user_phone
            )
            
            print(f"[TWILIO] ✅ SMS sent: {sms.sid}")
            
            return {
                "success": True,
                "sms_sid": sms.sid,
                "message": "Crisis resources sent via SMS",
                "user_id": user_id
            }
        
        except Exception as e:
            error_msg = str(e)
            print(f"[TWILIO] ❌ Error sending SMS: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
    
    def get_call_status(self, call_sid: str) -> Dict[str, Any]:
        """
        Get status of a call.
        
        Args:
            call_sid: Twilio call SID
            
        Returns:
            Dictionary with call status
        """
        if not self.client:
            return {"error": "Twilio not configured"}
        
        try:
            call = self.client.calls(call_sid).fetch()
            return {
                "call_sid": call.sid,
                "status": call.status,
                "duration": call.duration,
                "date_created": str(call.date_created),
                "to": call.to,
                "from": call.from_
            }
        except Exception as e:
            return {"error": str(e)}

    async def handle_emergency_response(self, call_sid: str, digit_pressed: str) -> Dict[str, Any]:
        """
        Handle response from crisis center operator after emergency call.
        
        Args:
            call_sid: Twilio call SID
            digit_pressed: Digit pressed by the crisis operator (1=acknowledge, 2=specialist)
        
        Returns:
            Status dict with response handling result
        """
        print(f"[TWILIO-RESPONSE] 📞 Handling response for call {call_sid}, digit={digit_pressed}")
        
        if digit_pressed == "1":
            return {
                "status": "acknowledged",
                "call_sid": call_sid,
                "action": "crisis_center_acknowledged",
                "message": "Crisis center acknowledged the alert"
            }
        elif digit_pressed == "2":
            return {
                "status": "specialist_transfer",
                "call_sid": call_sid,
                "action": "transfer_to_specialist",
                "message": "Transferring to specialist"
            }
        else:
            return {
                "status": "no_response",
                "call_sid": call_sid,
                "action": "none",
                "message": f"Unrecognized input: {digit_pressed}"
            }


# Global singleton instance
_twilio_service: Optional[TwilioService] = None


def get_twilio_service() -> TwilioService:
    """Get or create Twilio service instance (singleton)"""
    global _twilio_service
    if _twilio_service is None:
        _twilio_service = TwilioService()
    return _twilio_service
