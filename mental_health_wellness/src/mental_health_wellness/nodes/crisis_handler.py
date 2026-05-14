"""
Crisis Handler Node - Immediate safety intervention
HIGHEST PRIORITY - Handles all crisis situations
"""

from ..agent.state import MentalHealthState
from ..agent.prompts import PROMPTS
from ..services.twilio_whatsapp_crisis import get_crisis_whatsapp_service
import requests
import asyncio


async def get_location_from_ip_async(ip_address: str = None) -> dict:
    """Get location from IP address asynchronously"""
    try:
        # Try to get public IP if not provided
        if not ip_address or ip_address in ['127.0.0.1', 'localhost', '::1']:
            try:
                ip_response = requests.get('https://api.ipify.org?format=json', timeout=3)
                ip_address = ip_response.json().get('ip')
                print(f"[GEO]  Detected public IP: {ip_address}")
            except Exception as e:
                print(f"[GEO]  Could not auto-detect IP: {e}")
                return {'success': False, 'error': 'Could not detect IP'}
        
        # Look up location
        print(f"[GEO]  Looking up location for IP: {ip_address}")
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
                    'accuracy': '500 metres',
                    'method': 'IP-based (automatic, no permission needed)',
                    'ip': ip_address
                }
                print(f"[GEO]  Location found: {location['city']}, {location['country']}")
                return location
        
        print(f"[GEO]  ip-api returned: {data.get('message', 'Unknown error')}")
        return {'success': False, 'error': 'IP lookup failed'}
        
    except Exception as e:
        print(f"[GEO]  Error getting IP geolocation: {str(e)}")
        return {'success': False, 'error': str(e)}


async def handle_crisis(state: MentalHealthState) -> dict:
    """
    Handle crisis situations by detecting crisis severity.
    
    Purpose:
        - Detect crisis severity level
        - Send WhatsApp alert to crisis center
        - Set crisis flags for response generator
        - Route to response generator for LLM-generated empathetic response
    
    CRITICAL: This node NO LONGER generates the response directly.
    It sets crisis flags and routes to response_generator_node for LLM response generation.
    This ensures the LLM generates contextually appropriate crisis responses.
    
    Input State:
        - messages: Conversation history
        - user_id: For logging
    
    Output State:
        - crisis_level: "low", "medium", "high"
        - crisis_detected: True/False
        - whatsapp_alert_sent: Boolean for alert status
        - tools_used: Updated with crisis tools
        - (final_response NOT set - let LLM generate it)
    
    Risk Levels:
        - HIGH: Immediate danger (suicide, self-harm intent)
        - MEDIUM: Warning signs (hopelessness, giving up)
        - LOW: General distress
    """
    messages = state.get("messages", [])
    user_id = state.get("user_id", "unknown")
    
    last_message = messages[-1].content if messages else ""
    
    print(f"\n[NODE: CRISIS_HANDLER]  CRISIS RESPONSE ACTIVATED")
    print(f"[NODE: CRISIS_HANDLER] User: {user_id}")
    print(f"[NODE: CRISIS_HANDLER] Message: \"{last_message[:80]}...\"")
    
    try:
        # ============================================
        # CRISIS CHECK: RELY ON AGENT JUDGMENT
        # ============================================
        
        # 1. Check if Agent set a crisis level
        agent_crisis_level = state.get("crisis_level", "low")
        
        # 2. Check if Agent called crisis tools explicitly
        tools_used = state.get("tools_used", [])
        agent_called_crisis_tools = "handle_crisis" in tools_used
        
        print(f"[NODE: CRISIS_HANDLER]  Agent Crisis Level: {agent_crisis_level.upper()}")
        print(f"[NODE: CRISIS_HANDLER]  Agent Tools: {tools_used}")
        
        # Determine final crisis status
        final_crisis_level = "low"
        crisis_pre_screened = state.get("crisis_pre_screened", False)
        
        if crisis_pre_screened:
            final_crisis_level = state.get("crisis_level", "medium")
            print(f"[NODE: CRISIS_HANDLER]  Pre-screener trusted  using level: {final_crisis_level.upper()}")
        elif agent_called_crisis_tools:
            final_crisis_level = "high"
            print(f"[NODE: CRISIS_HANDLER]  Agent explicitly called crisis tools - ESCALATING TO HIGH RISK")
        elif agent_crisis_level in ["medium", "high"]:
            final_crisis_level = agent_crisis_level
            print(f"[NODE: CRISIS_HANDLER]  Agent set risk level to {agent_crisis_level.upper()}")
            
        
        # Only treat as crisis if risk level is medium or high
        if final_crisis_level in ["medium", "high"]:
            print(f"[NODE: CRISIS_HANDLER]  Crisis detected - routing to LLM for response generation")
            
            # ============================================
            # SEND WHATSAPP CRISIS ALERT
            # ============================================
            try:
                whatsapp_service = get_crisis_whatsapp_service()

                # Build enriched user_details dict  include all voice + text signals
                voice_features  = state.get("voice_features") or {}
                voice_processed = bool(voice_features) and state.get("voice_processed", False)

                user_details = {
                    "emotion_text":     state.get("emotion", "unknown"),
                    "emotion_fused":    state.get("fused_emotion", state.get("emotion", "unknown")),
                    "sentiment":        state.get("sentiment", "negative"),
                    "intensity":        f"{state.get('fused_intensity', state.get('intensity', 0.9)):.0%}",
                    "message_preview":  last_message[:120],
                }

                # Append voice acoustic signals when voice was present
                if voice_processed:
                    distress_idx = float(voice_features.get("distress_index", 0.0))
                    pause_den    = float(voice_features.get("pause_density", 0.25))
                    v_emotion    = voice_features.get("emotion", "unknown")
                    v_conf       = float(voice_features.get("confidence", 0.0))
                    conflict     = v_emotion != state.get("emotion", "neutral")

                    user_details.update({
                        "source":              "Voice + Text Message",
                        "voice_emotion":       f"{v_emotion} (conf={v_conf:.0%})",
                        "distress_index":      f"{distress_idx:.2f}/1.00 {' HIGH' if distress_idx > 0.6 else 'moderate' if distress_idx > 0.35 else 'low'}",
                        "pause_density":       f"{pause_den:.2f} ({'hesitant/slow speech' if pause_den > 0.35 else 'normal'})",
                        "voice_text_conflict": "YES  voice and text disagreed on emotion (may be masking)" if conflict else "No  voice and text aligned",
                    })
                else:
                    user_details["source"] = "Text Message Only"

                
                alert_result = whatsapp_service.send_crisis_alert_voice_message(
                    user_id=user_id,
                    crisis_level=final_crisis_level,
                    user_details=user_details
                )
                
                if alert_result.get("success"):
                    print(f"[NODE: CRISIS_HANDLER]  WhatsApp alert sent (SID: {alert_result.get('message_sid')})")
                else:
                    print(f"[NODE: CRISIS_HANDLER]  WhatsApp alert failed: {alert_result.get('error')}")
                
                # ============================================
                # SEND LOCATION ALERT (IP-BASED AUTO)
                # ============================================
                # Send automatic IP-based location since GPS can't be requested from backend
                # Frontend will handle GPS separately when available
                print(f"[NODE: CRISIS_HANDLER]  Sending automatic IP-based location alert...")
                try:
                    location_data = await get_location_from_ip_async()
                    
                    if location_data.get('success'):
                        location_result = whatsapp_service.send_location_alert(
                            user_id=user_id,
                            latitude=location_data['latitude'],
                            longitude=location_data['longitude'],
                            city=location_data.get('city'),
                            region=location_data.get('region'),
                            country=location_data.get('country'),
                            accuracy=location_data.get('accuracy'),
                            crisis_level=final_crisis_level,
                            method="IP-based (automatic, no permission needed)"
                        )
                        
                        if location_result.get("success"):
                            print(f"[NODE: CRISIS_HANDLER]  Location alert sent via {location_result.get('channel')} (SID: {location_result.get('message_sid')})")
                            print(f"[NODE: CRISIS_HANDLER]  Maps: {location_result.get('maps_link')}")
                        else:
                            print(f"[NODE: CRISIS_HANDLER]  Location alert failed: {location_result.get('error')}")
                    else:
                        print(f"[NODE: CRISIS_HANDLER]  Could not determine location: {location_data.get('error')}")
                        
                except Exception as location_error:
                    print(f"[NODE: CRISIS_HANDLER]  Error sending location alert: {location_error}")
                
            except Exception as alert_error:
                print(f"[NODE: CRISIS_HANDLER]  Error sending WhatsApp alert: {alert_error}")
            
            # Return crisis flags - DO NOT set final_response, let LLM generate it
            return {
                "crisis_level": final_crisis_level,
                "crisis_detected": True,
                "tools_used": ["handle_crisis"],
                "whatsapp_alert_sent": alert_result.get("success") if 'alert_result' in locals() else False
            }
        else:
            # Not a crisis but high distress (e.g. panic attack, extreme anxiety).
            # The crisis_handler was triggered by the intensity router, NOT the pre-screener.
            # We must generate a supportive response here because the pipeline skips
            # response_generator after crisis_handler.
            emotion = state.get("fused_emotion", state.get("emotion", "anxiety"))
            print(f"[NODE: CRISIS_HANDLER]  High-distress (non-crisis) detected  generating supportive response (emotion: {emotion})")

            # Read the actual techniques selected by technique_selector so the response
            # text references the exact same names shown in the UI cards.
            techniques_by_category = state.get("recommended_techniques_by_category", {})
            technique_names = []
            for cat, tech in techniques_by_category.items():
                name = tech.get("name") if isinstance(tech, dict) else None
                if name:
                    technique_names.append(name)

            if technique_names:
                tech_list = " and ".join(f"**{n}**" for n in technique_names[:2])
                technique_mention = f"I've also pulled up {tech_list} for you below  they're great for moments like this."
            else:
                technique_mention = "I've pulled up some grounding exercises below that can really help in moments like this."

            if "anxiety" in emotion or "fear" in emotion:
                supportive_response = (
                    "I can feel how intense this is for you right now. Panic attacks are terrifying in the moment, but they are temporary and they will pass. \n\n"
                    f"{technique_mention}\n\n"
                    "For right now  breathe in slowly through your nose for 4 counts, hold for 4, and breathe out for 6. Focus only on that breath.\n\n"
                    "You're safe. I'm right here with you. Tell me how you're feeling right now."
                )
            elif "anger" in emotion:
                supportive_response = (
                    "I can sense you're in a really overwhelming place right now. It's okay to feel this way. \n\n"
                    f"{technique_mention}\n\n"
                    "Let's take a moment  try breathing deeply a few times and give yourself permission to step back. I'm here with you."
                )
            else:
                supportive_response = (
                    "I can see you're going through something really intense right now. I'm here with you. \n\n"
                    f"{technique_mention}\n\n"
                    "Take a slow, deep breath with me. You don't have to face this alone. What's happening for you right now?"
                )

            return {
                "crisis_level": final_crisis_level,
                "crisis_detected": False,
                "final_response": supportive_response,
            }
        
    except Exception as e:
        print(f"[NODE: CRISIS_HANDLER]  Error: {e}")
        
        # On error, just set crisis flags - LLM will handle response generation
        return {
            "crisis_level": "medium",
            "crisis_detected": True,
            "tools_used": ["handle_crisis"]
        }



