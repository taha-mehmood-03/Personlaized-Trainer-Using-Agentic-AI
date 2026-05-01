"""
Crisis API Endpoints - Handle emergency resources and direct calling
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
import requests

from ..services import get_twilio_service, CountryDetector
from ..services.twilio_whatsapp_crisis import get_crisis_whatsapp_service
from ..tools.crisis_tools import get_crisis_resources

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crisis", tags=["crisis"])


# ============================================
# IP-BASED GEOLOCATION HELPER
# ============================================

def get_location_from_ip(ip_address: Optional[str] = None) -> Dict[str, Any]:
    """
    Get precise location from IP address using free IP geolocation service
    No user permission needed - works instantly
    
    Args:
        ip_address: Optional IP to lookup. If None, will use client's IP
        
    Returns:
        Dictionary with latitude, longitude, city, region, country
    """
    try:
        # Get client IP if not provided, or if it's localhost
        if not ip_address or ip_address in ['127.0.0.1', 'localhost', '::1']:
            try:
                print(f"[GEO] 🌐 Detecting public IP (provided: {ip_address})...")
                ip_response = requests.get('https://api.ipify.org?format=json', timeout=3)
                ip_address = ip_response.json().get('ip')
                print(f"[GEO] ✅ Detected public IP: {ip_address}")
            except Exception as e:
                print(f"[GEO] ⚠️ Could not auto-detect IP: {e}")
                return {'success': False, 'error': 'Could not detect IP'}
        
        # Use ip-api.com for geolocation (free, no key needed, accurate)
        print(f"[GEO] 🔍 Looking up location for IP: {ip_address}")
        geo_response = requests.get(
            f'http://ip-api.com/json/{ip_address}?fields=status,lat,lon,city,regionName,country,isp',
            timeout=5
        )
        
        if geo_response.status_code == 200:
            data = geo_response.json()
            if data.get('status') == 'success':
                location = {
                    'success': True,
                    'latitude': data.get('lat'),
                    'longitude': data.get('lon'),
                    'city': data.get('city', 'Unknown'),
                    'region': data.get('regionName', 'Unknown'),
                    'country': data.get('country', 'Unknown'),
                    'isp': data.get('isp', 'Unknown'),
                    'accuracy': '±500 metres',  # Typical IP geolocation accuracy
                    'method': 'IP-based (automatic, no permission needed)',
                    'ip': ip_address
                }
                print(f"[GEO] [OK] Location found: {location['city']}, {location['country']}")
                return location
        
        print(f"[GEO] ⚠️ ip-api returned: {data.get('message', 'Unknown error')}")
        return {'success': False, 'error': 'IP lookup failed'}
        
    except Exception as e:
        logger.error(f"[GEO] ❌ Error getting IP geolocation: {str(e)}")
        print(f"[GEO] ❌ Exception: {e}")
        return {
            'success': False,
            'error': str(e),
            'latitude': None,
            'longitude': None
        }


class LocationAlertRequest(BaseModel):
    """Request to send a location-based WhatsApp alert"""
    user_id: str = Field(..., description="User ID who triggered the crisis")
    latitude: float = Field(..., description="GPS latitude from browser geolocation")
    longitude: float = Field(..., description="GPS longitude from browser geolocation")
    accuracy: Optional[float] = Field(None, description="Geolocation accuracy in metres")
    crisis_level: str = Field("high", description="Crisis level: medium or high")


class AutoLocationRequest(BaseModel):
    """Request to send location alert using automatic IP-based geolocation"""
    user_id: str = Field(..., description="User ID who triggered the crisis")
    crisis_level: str = Field("high", description="Crisis level: medium or high")
    ip_address: Optional[str] = Field(None, description="Optional IP address to lookup. If None, auto-detects.")


class CrisisResourceRequest(BaseModel):
    """Request for crisis resources"""
    country_code: Optional[str] = Field("US", description="ISO 3166-1 alpha-2 country code")
    user_id: Optional[str] = Field("anonymous", description="User ID for tracking")


class CrisisCallRequest(BaseModel):
    """Request to initiate a crisis call"""
    user_phone: str = Field(..., description="User's phone in E.164 format (+1234567890)")
    hotline_number: Optional[str] = Field(None, description="Specific hotline to call. If None, uses primary hotline")
    country_code: Optional[str] = Field("US", description="ISO 3166-1 alpha-2 country code")
    user_id: Optional[str] = Field("anonymous", description="User ID for tracking")


class CrisisSMSRequest(BaseModel):
    """Request to send crisis resources via SMS"""
    user_phone: str = Field(..., description="User's phone in E.164 format")
    country_code: Optional[str] = Field("US", description="ISO 3166-1 alpha-2 country code")
    user_id: Optional[str] = Field("anonymous", description="User ID for tracking")


class CountryDetectionRequest(BaseModel):
    """Request to detect user's country"""
    phone: Optional[str] = Field(None, description="Phone number for detection")
    ip_address: Optional[str] = Field(None, description="IP address for detection")
    user_data: Optional[Dict[str, Any]] = Field(None, description="User profile data")


@router.post("/resources")
async def get_resources(request: CrisisResourceRequest) -> Dict[str, Any]:
    """
    Get crisis resources for a specific country.
    
    Returns:
        Crisis resources with hotlines, text lines, and support options
    """
    try:
        print(f"[API] 📞 Crisis resources request for {request.country_code}")
        
        resources = get_crisis_resources(request.country_code)
        
        return {
            "success": True,
            "country_code": request.country_code,
            "resources": resources,
            "user_id": request.user_id
        }
    except Exception as e:
        logger.error(f"Error fetching crisis resources: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect-country")
async def detect_country(request: CountryDetectionRequest) -> Dict[str, Any]:
    """
    Detect user's country from phone, IP, or profile data.
    
    Returns:
        Detected country code
    """
    try:
        print(f"[API] 🌍 Country detection request")
        
        country = CountryDetector.detect(
            phone=request.phone,
            ip_address=request.ip_address,
            user_data=request.user_data
        )
        
        print(f"[API] ✅ Detected country: {country}")
        
        return {
            "success": True,
            "country_code": country,
            "detected_from": "phone" if request.phone else ("ip" if request.ip_address else "profile")
        }
    except Exception as e:
        logger.error(f"Error detecting country: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/initiate-call")
async def initiate_crisis_call(request: CrisisCallRequest) -> Dict[str, Any]:
    """
    Initiate a direct call to crisis hotline via Twilio.
    
    Args:
        user_phone: User's phone number in E.164 format
        hotline_number: Crisis hotline number to connect to
        country_code: Country code for context
        user_id: User ID for tracking
    
    Returns:
        Call status and details
    """
    try:
        print(f"[API] 📞 Crisis call initiation for user {request.user_id}")
        
        # Get primary hotline if not specified
        hotline = request.hotline_number
        if not hotline:
            resources = get_crisis_resources(request.country_code)
            hotline = resources.get("primary_hotline", {}).get("number", "988")
            print(f"[API] 🔍 Using primary hotline: {hotline}")
        
        # Initiate call via Twilio
        twilio_service = get_twilio_service()
        result = twilio_service.initiate_crisis_call(
            user_phone=request.user_phone,
            hotline_number=hotline,
            user_id=request.user_id,
            country=request.country_code
        )
        
        return {
            "success": result.get("success", False),
            "call_sid": result.get("call_sid"),
            "message": result.get("message"),
            "error": result.get("error"),
            "user_id": request.user_id
        }
    except Exception as e:
        logger.error(f"Error initiating crisis call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send-sms")
async def send_crisis_sms(request: CrisisSMSRequest) -> Dict[str, Any]:
    """
    Send crisis resources via SMS to user's phone.
    
    Args:
        user_phone: User's phone number in E.164 format
        country_code: Country code for context
        user_id: User ID for tracking
    
    Returns:
        SMS status
    """
    try:
        print(f"[API] 📱 Crisis SMS request for user {request.user_id}")
        
        # Build SMS message with country-specific resources
        resources = get_crisis_resources(request.country_code)
        hotline = resources.get("primary_hotline", {})
        
        message = f"""🆘 CRISIS SUPPORT - {request.country_code}

{hotline.get('name', 'Crisis Hotline')}
📞 {hotline.get('number', 'N/A')} 

Available: {hotline.get('available', '24/7')}

You are not alone. Help is available now."""
        
        # Send via Twilio
        twilio_service = get_twilio_service()
        result = twilio_service.send_crisis_sms(
            user_phone=request.user_phone,
            message=message,
            user_id=request.user_id
        )
        
        return {
            "success": result.get("success", False),
            "sms_sid": result.get("sms_sid"),
            "message": result.get("message"),
            "error": result.get("error"),
            "user_id": request.user_id
        }
    except Exception as e:
        logger.error(f"Error sending crisis SMS: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/call-status/{call_sid}")
async def get_call_status(call_sid: str) -> Dict[str, Any]:
    """
    Get status of a Twilio call.
    
    Args:
        call_sid: Twilio call SID
    
    Returns:
        Call status and details
    """
    try:
        print(f"[API] 📊 Checking call status: {call_sid}")
        
        twilio_service = get_twilio_service()
        result = twilio_service.get_call_status(call_sid)
        
        return {
            "success": "error" not in result,
            "call_status": result
        }
    except Exception as e:
        logger.error(f"Error getting call status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def crisis_health() -> Dict[str, Any]:
    """Health check for crisis endpoints"""
    twilio_service = get_twilio_service()
    twilio_configured = twilio_service.client is not None
    
    return {
        "status": "ok",
        "crisis_endpoints": "available",
        "twilio_configured": twilio_configured
    }

# ============================================
# PAKISTAN CRISIS CENTER INTEGRATION
# ============================================

class PakistanCrisisAlertRequest(BaseModel):
    """Request to alert Pakistan crisis center"""
    user_id: str = Field(..., description="User ID")
    user_name: str = Field(..., description="User's name")
    crisis_level: str = Field(..., description="Crisis level: low, medium, high, critical")
    message_excerpt: str = Field(..., description="User's message that triggered alert")
    user_phone: Optional[str] = Field(None, description="User's phone for callback")


class TwilioCrisisCallRequest(BaseModel):
    """Request to initiate emergency call to Pakistan crisis center"""
    user_id: str = Field(..., description="User ID")
    user_name: str = Field(..., description="User's name")
    crisis_level: str = Field("high", description="Crisis severity level")
    message_excerpt: str = Field(..., description="Message triggering crisis detection")
    user_phone: Optional[str] = Field(None, description="User's phone")


@router.post("/pakistan/alert")
async def alert_pakistan_crisis_center(request: PakistanCrisisAlertRequest) -> Dict[str, Any]:
    """
    Alert Pakistan's Tele-Tabeeb 1123 crisis center.
    Initiates automatic voice call with crisis details.
    
    This endpoint:
    1. Detects a user in crisis (self-harm ideation)
    2. Calls Tele-Tabeeb 1123 with automated alert
    3. Provides crisis operator with user details
    4. Records conversation for documentation
    
    Args:
        user_id: User ID
        user_name: User's name
        crisis_level: Crisis severity (low/medium/high/critical)
        message_excerpt: User's concerning message
        user_phone: Optional user phone for callback
    
    Returns:
        Call initiation status with call SID
    """
    try:
        print(f"\n{'='*60}")
        print(f"[API-CRISIS] 🚨 Pakistan Crisis Alert Request")
        print(f"[API-CRISIS] User: {request.user_name} (ID: {request.user_id})")
        print(f"[API-CRISIS] Level: {request.crisis_level}")
        print(f"{'='*60}")
        
        twilio_service = get_twilio_service()
        
        # Initiate emergency call to Tele-Tabeeb 1123
        result = await twilio_service.call_pakistan_crisis_center(
            user_id=request.user_id,
            user_name=request.user_name,
            crisis_level=request.crisis_level,
            message_excerpt=request.message_excerpt,
            user_phone=request.user_phone,
        )
        
        if result.get("success"):
            print(f"[API-CRISIS] ✅ Emergency call to Pakistan crisis center initiated")
            print(f"[API-CRISIS] Call SID: {result.get('call_sid')}")
        else:
            print(f"[API-CRISIS] ⚠️ Call initiation failed: {result.get('error')}")
        
        return result
    
    except Exception as e:
        logger.error(f"Error alerting Pakistan crisis center: {str(e)}")
        print(f"[API-CRISIS] ❌ Exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pakistan/whatsapp-alert")
async def alert_pakistan_whatsapp(request: PakistanCrisisAlertRequest) -> Dict[str, Any]:
    """
    Send WhatsApp alert to Pakistan's Tele-Tabeeb 1123 crisis center.
    Fallback method if voice call fails.
    
    Args:
        user_id: User ID
        user_name: User's name
        crisis_level: Crisis severity
        message_excerpt: User's concerning message
        user_phone: Optional user phone
    
    Returns:
        WhatsApp message status
    """
    try:
        print(f"[API-CRISIS] 📱 Sending WhatsApp alert to Pakistan crisis center")
        
        twilio_service = get_twilio_service()
        
        # Send WhatsApp alert
        result = await twilio_service.send_crisis_alert_whatsapp(
            crisis_center_number=twilio_service.whatsapp_number,
            user_id=request.user_id,
            user_name=request.user_name,
            crisis_level=request.crisis_level,
            message_excerpt=request.message_excerpt,
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Error sending WhatsApp alert: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/twilio/response")
async def handle_twilio_response(request: Request) -> Dict[str, Any]:
    """
    Handle response from Twilio crisis center call.
    Crisis operator presses 1 to acknowledge, 2 for specialist transfer.
    
    Args:
        request: Twilio webhook request with digits pressed
    
    Returns:
        Response handling status
    """
    try:
        # Parse form data from Twilio webhook
        form_data = await request.form()
        digit_pressed = form_data.get("Digits", "")
        call_sid = form_data.get("CallSid", "")
        
        print(f"[TWILIO-RESPONSE] 📞 Response from crisis center")
        print(f"[TWILIO-RESPONSE] Call SID: {call_sid}")
        print(f"[TWILIO-RESPONSE] Digit pressed: {digit_pressed}")
        
        twilio_service = get_twilio_service()
        result = await twilio_service.handle_emergency_response(call_sid, digit_pressed)
        
        return result
    
    except Exception as e:
        logger.error(f"Error handling Twilio response: {str(e)}")
        return {"status": "error", "error": str(e)}


@router.post("/twilio/status")
async def handle_twilio_status(request: Request) -> Dict[str, Any]:
    """
    Handle Twilio call status callback.
    Tracks: initiated → ringing → answered → completed/failed
    
    Args:
        request: Twilio webhook request with call status
    
    Returns:
        Status acknowledgment
    """
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid", "")
        call_status = form_data.get("CallStatus", "")
        call_duration = form_data.get("CallDuration", "0")
        
        print(f"[TWILIO-STATUS] 📊 Call Status Update")
        print(f"[TWILIO-STATUS] Call SID: {call_sid}")
        print(f"[TWILIO-STATUS] Status: {call_status}")
        print(f"[TWILIO-STATUS] Duration: {call_duration}s")
        
        # Log to database if needed
        # await save_call_status(call_sid, call_status, call_duration)
        
        return {
            "status": "acknowledged",
            "call_sid": call_sid,
            "call_status": call_status,
        }
    
    except Exception as e:
        logger.error(f"Error handling Twilio status: {str(e)}")
        return {"status": "error", "error": str(e)}


@router.post("/test-whatsapp-alert")
async def test_whatsapp_alert(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test endpoint to verify WhatsApp crisis alert is working.
    
    Args:
        user_id: Test user ID
        crisis_level: "high" or "medium"
    
    Returns:
        WhatsApp alert status
    """
    try:
        from ..services.twilio_whatsapp_crisis import get_crisis_whatsapp_service
        
        user_id = request.get("user_id", "test-user")
        crisis_level = request.get("crisis_level", "medium")
        
        print(f"\n[TEST] 🧪 Testing WhatsApp crisis alert")
        print(f"[TEST] User ID: {user_id}")
        print(f"[TEST] Crisis Level: {crisis_level}")
        
        whatsapp_service = get_crisis_whatsapp_service()
        
        # Check if service is configured
        if not whatsapp_service.client:
            return {
                "success": False,
                "error": "WhatsApp service not configured - check Twilio credentials in .env",
                "configured": False,
            }
        
        test_details = {
            "emotion_text": "test_emotion",
            "emotion_fused": "sadness",
            "sentiment": "negative",
            "intensity": "90%",
            "message_preview": "This is a test crisis message for WhatsApp alert verification",
            "source": "Test Message",
        }
        
        result = whatsapp_service.send_crisis_alert_voice_message(
            user_id=user_id,
            crisis_level=crisis_level,
            user_details=test_details
        )
        
        print(f"\n[TEST] Result: {result}")
        
        return {
            "success": result.get("success", False),
            "message_sid": result.get("message_sid"),
            "channel": result.get("channel", "unknown"),
            "status": result.get("status", "unknown"),
            "error": result.get("error"),
            "configured": True,
        }
    
    except Exception as e:
        logger.error(f"Error testing WhatsApp alert: {str(e)}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


# ============================================
# LOCATION-BASED CRISIS ALERT
# ============================================

@router.post("/send-location")
async def send_location_alert(request: LocationAlertRequest) -> Dict[str, Any]:
    """
    Send a WhatsApp alert containing the user's GPS location when a crisis is detected.

    Called by the frontend immediately after receiving crisis_detected=true from
    the streaming endpoint. The browser's geolocation API supplies lat/lng.

    The resulting WhatsApp message includes:
      - Crisis level badge
      - User ID + timestamp
      - Latitude / Longitude
      - Clickable Google Maps link

    Returns:
        success flag, message_sid, channel used, and maps_link
    """
    try:
        print(f"\n[CRISIS-LOC] 📍 GPS LOCATION ALERT - Browser Geolocation")
        print(f"[CRISIS-LOC] 🎯 PRECISE LOCATION FROM USER'S BROWSER GPS")
        print(f"[CRISIS-LOC]   User:     {request.user_id}")
        print(f"[CRISIS-LOC]   Level:    {request.crisis_level.upper()}")
        print(f"[CRISIS-LOC]   LatLng:   {request.latitude:.5f}, {request.longitude:.5f}")
        print(f"[CRISIS-LOC]   Link:     https://www.google.com/maps?q={request.latitude},{request.longitude}")
        if request.accuracy:
            print(f"[CRISIS-LOC]   Accuracy: ±{request.accuracy:.0f} m (Precise GPS)")
        else:
            print(f"[CRISIS-LOC]   Accuracy: ±5-20 m (High precision GPS)")

        whatsapp_service = get_crisis_whatsapp_service()

        if not whatsapp_service.client:
            print(f"[CRISIS-LOC] ⚠️  Twilio not configured — skipping location alert")
            return {
                "success": False,
                "error": "WhatsApp service not configured — check Twilio credentials in .env",
                "configured": False,
            }

        result = whatsapp_service.send_location_alert(
            user_id=request.user_id,
            latitude=request.latitude,
            longitude=request.longitude,
            accuracy=request.accuracy,
            crisis_level=request.crisis_level,
            method="GPS",  # Explicitly mark as GPS-based location from browser
        )

        if result.get("success"):
            print(f"[CRISIS-LOC] ✅ Location alert sent via {result.get('channel')} — SID: {result.get('message_sid')}")
            print(f"[CRISIS-LOC]   Maps link: {result.get('maps_link')}")
        else:
            print(f"[CRISIS-LOC] ❌ Location alert failed: {result.get('error')}")

        # Ensure response is properly JSON serializable
        try:
            response = {
                "success": result.get("success", False),
                "message_sid": str(result.get("message_sid", "")),
                "channel": str(result.get("channel", "")),
                "maps_link": str(result.get("maps_link", "")),
                "timestamp": str(result.get("timestamp", "")),
                "latitude": float(result.get("latitude", 0.0)),
                "longitude": float(result.get("longitude", 0.0)),
                "error": str(result.get("error", "")) if result.get("error") else None,
            }
            return response
        except Exception as e:
            print(f"[CRISIS-LOC] ⚠️ Error formatting response: {e}")
            return {
                "success": result.get("success", False),
                "error": "Error formatting response",
                "message_sid": None
            }

    except Exception as e:
        logger.error(f"Error sending location alert: {str(e)}")
        import traceback
        print(f"[CRISIS-LOC] ❌ Exception: {e}")
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "message_sid": None
        }

# ============================================
# IP-BASED AUTO LOCATION ALERT (NO PERMISSION NEEDED)
# ============================================

@router.post("/send-location-auto")
async def send_location_auto(request: AutoLocationRequest, req: Request) -> Dict[str, Any]:
    """
    Send WhatsApp crisis alert with AUTOMATIC IP-based location.
    
    NO browser permission required!
    NO user action needed!
    
    Called automatically when crisis is detected.
    Detects user's location from IP address and sends it to crisis center via WhatsApp.
    
    The resulting WhatsApp message includes:
      - Crisis level badge
      - User ID + timestamp
      - City, Region, Country
      - Latitude / Longitude
      - Clickable Google Maps link
      - Accuracy: ±500 metres (typical IP geolocation accuracy)
    
    Args:
        request: AutoLocationRequest with user_id, crisis_level, optional ip_address
        req: FastAPI Request object to extract client IP if needed
    
    Returns:
        success flag, message_sid, channel used, location details, and maps_link
    """
    try:
        # Get IP address: priority is request.ip_address > client IP from request
        ip_to_lookup = request.ip_address
        if not ip_to_lookup:
            # Extract client IP from request headers
            client_ip = req.client.host if req.client else None
            ip_to_lookup = client_ip
        
        print(f"\n[AUTO-LOC] 🔄 IP-BASED FALLBACK LOCATION ALERT")
        print(f"[AUTO-LOC] ⚠️ GPS PERMISSION DENIED OR UNAVAILABLE - Using IP-based fallback")
        print(f"[AUTO-LOC]   User:     {request.user_id}")
        print(f"[AUTO-LOC]   Level:    {request.crisis_level.upper()}")
        print(f"[AUTO-LOC]   IP:       {ip_to_lookup}")
        
        # Get location from IP
        location = get_location_from_ip(ip_to_lookup)
        
        if not location.get('success'):
            print(f"[AUTO-LOC] ⚠️ Location lookup failed: {location.get('error')}")
            return {
                "success": False,
                "error": location.get('error', 'Could not determine location from IP'),
                "message_sid": None,
                "location": location
            }
        
        print(f"[AUTO-LOC] ✅ Location found: {location['city']}, {location['region']}, {location['country']}")
        
        # Send WhatsApp with location
        whatsapp_service = get_crisis_whatsapp_service()
        
        if not whatsapp_service.client:
            print(f"[AUTO-LOC] ⚠️ Twilio not configured")
            return {
                "success": False,
                "error": "WhatsApp service not configured — check Twilio credentials in .env",
                "configured": False,
                "location": location
            }
        
        result = whatsapp_service.send_location_alert(
            user_id=request.user_id,
            latitude=location['latitude'],
            longitude=location['longitude'],
            city=location['city'],
            region=location['region'],
            country=location['country'],
            accuracy=location['accuracy'],
            crisis_level=request.crisis_level,
            method=location['method']
        )
        
        if result.get("success"):
            print(f"[AUTO-LOC] ✅ Auto location alert sent via {result.get('channel')} — SID: {result.get('message_sid')}")
            print(f"[AUTO-LOC]   Location: {location['city']}, {location['country']}")
            print(f"[AUTO-LOC]   LatLng: {location['latitude']}, {location['longitude']}")
            print(f"[AUTO-LOC]   Maps: {result.get('maps_link')}")
        else:
            print(f"[AUTO-LOC] ❌ WhatsApp send failed: {result.get('error')}")
        
        return {
            "success": result.get("success", False),
            "message_sid": result.get("message_sid"),
            "channel": result.get("channel", "unknown"),
            "status": result.get("status"),
            "error": result.get("error"),
            "location": location,
            "maps_link": result.get("maps_link"),
            "user_id": request.user_id,
            "timestamp": result.get("timestamp")
        }
    
    except Exception as e:
        logger.error(f"Error in send_location_auto: {str(e)}")
        import traceback
        print(f"[AUTO-LOC] ❌ Exception: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))