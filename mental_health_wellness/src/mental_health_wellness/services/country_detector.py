"""
Country Detection Utility - Detect user location and provide region-specific resources
"""

import os
from typing import Dict, Any, Optional
from enum import Enum


class Country(str, Enum):
    """Supported countries"""
    US = "US"
    CA = "CA"
    PK = "PK"
    GB = "GB"
    AU = "AU"
    UNKNOWN = "PK"  # Default fallback


class CountryDetector:
    """Detect user country from various sources"""
    
    @staticmethod
    def from_phone_number(phone: str) -> str:
        """
        Detect country from phone number country code.
        
        Args:
            phone: Phone number in E.164 format (+1234567890)
        
        Returns:
            ISO 3166-1 alpha-2 country code
        """
        # Remove + and get country code
        phone_clean = phone.lstrip('+')
        
        # Country code mapping (first 1-3 digits)
        country_codes = {
            "1": "US",      # +1 (US & Canada)
            "44": "GB",     # +44 (UK)
            "61": "AU",     # +61 (Australia)
            "92": "PK",     # +92 (Pakistan)
        }
        
        # Check 3-digit code first, then 2-digit, then 1-digit
        if phone_clean.startswith("1"):
            return "US"  # Default to US for +1 (could also be CA)
        
        for code_len in [3, 2, 1]:
            code = phone_clean[:code_len]
            if code in country_codes:
                return country_codes[code]
        
        return "US"  # Default fallback
    
    @staticmethod
    def from_ip_address(ip_address: str) -> str:
        """
        Detect country from IP address using GeoIP2.
        Requires MaxMind GeoLite2 database.
        
        Args:
            ip_address: IPv4 or IPv6 address
        
        Returns:
            ISO 3166-1 alpha-2 country code
        """
        try:
            import geoip2.database
            
            # Path to MaxMind database (requires separate setup)
            db_path = os.getenv("GEOIP_DB_PATH", "")
            
            if not db_path or not os.path.exists(db_path):
                print(f"[GEO]  GeoIP database not found at {db_path}")
                return "US"
            
            with geoip2.database.Reader(db_path) as reader:
                response = reader.country(ip_address)
                country_code = response.country.iso_code
                print(f"[GEO]  Detected country from IP {ip_address}: {country_code}")
                return country_code
        
        except Exception as e:
            print(f"[GEO]  Could not detect country from IP: {str(e)}")
            return "US"
    
    @staticmethod
    def from_user_profile(user_data: Dict[str, Any]) -> str:
        """
        Detect country from user profile data.
        
        Args:
            user_data: User profile dictionary with possible 'country', 'location', 'phone' fields
        
        Returns:
            ISO 3166-1 alpha-2 country code
        """
        # Check explicit country field
        if "country" in user_data:
            return user_data["country"].upper()
        
        if "country_code" in user_data:
            return user_data["country_code"].upper()
        
        # Check phone number
        if "phone" in user_data and user_data["phone"]:
            return CountryDetector.from_phone_number(user_data["phone"])
        
        # Check location field
        if "location" in user_data:
            location = user_data["location"].lower()
            # Simple country name mapping
            country_names = {
                "pakistan": "PK",
                "karachi": "PK",
                "lahore": "PK",
                "islamabad": "PK",
                "uk": "GB",
                "united kingdom": "GB",
                "australia": "AU",
                "sydney": "AU",
                "canada": "CA",
                "toronto": "CA"
            }
            for name, code in country_names.items():
                if name in location:
                    return code
        
        return "US"  # Default fallback
    
    @staticmethod
    def detect(
        phone: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Detect country using multiple methods (priority order).
        
        Args:
            phone: User's phone number
            ip_address: User's IP address
            user_data: User profile data
        
        Returns:
            ISO 3166-1 alpha-2 country code
        """
        # Priority: user_data > phone > ip_address
        
        if user_data:
            country = CountryDetector.from_user_profile(user_data)
            if country != "US":  # If not default
                return country
        
        if phone:
            return CountryDetector.from_phone_number(phone)
        
        if ip_address:
            return CountryDetector.from_ip_address(ip_address)
        
        return "US"  # Final fallback


def format_phone_for_country(phone: str, country: str) -> str:
    """
    Format phone number for a specific country's dialing.
    
    Args:
        phone: Phone number (may or may not have country code)
        country: ISO 3166-1 alpha-2 country code
    
    Returns:
        Phone number in E.164 format
    """
    phone_clean = ''.join(filter(str.isdigit, phone))
    
    # Country code mapping
    country_codes = {
        "US": "+1",
        "CA": "+1",
        "GB": "+44",
        "AU": "+61",
        "PK": "+92",
    }
    
    country_code = country_codes.get(country.upper(), "+1")
    
    # Check if already has country code
    if phone.startswith("+"):
        return phone
    
    # Add country code if needed
    if not phone.startswith("1") and country.upper() in ["US", "CA"]:
        phone_clean = phone_clean.lstrip("1")  # Remove leading 1 if present
    
    return f"{country_code}{phone_clean}"
