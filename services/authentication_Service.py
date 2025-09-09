import logging
import xml.etree.ElementTree as ET

from odoo.http import request

_logger = logging.getLogger(__name__)

class AuthenticationService:
    """Service for handling authentication logic"""

    @staticmethod
    def get_token(api_key):
        """Authenticate and get access token"""
        try:
            user_id = request.env["res.users.apikeys"]._check_credentials(scope="rpc", key=api_key)
            if user_id:
                access_token = request.env["api.access_token"].find_or_create_token(user_id=user_id, create=True)
                return access_token
        except Exception as e:
            _logger.error("Authentication error: %s", e)
        return None

    @staticmethod
    def extract_api_key_from_soap(xml_data):
        """Extract API key from SOAP header"""
        try:
            ns = {
                "wsse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
                "soapenv": "http://schemas.xmlsoap.org/soap/envelope/"
            }
            root = ET.fromstring(xml_data)
            password_el = root.find(".//wsse:Password", ns)
            if password_el is not None:
                return password_el.text.strip()
        except Exception as e:
            _logger.error("Failed to parse SOAP XML: %s", e)
        return None
