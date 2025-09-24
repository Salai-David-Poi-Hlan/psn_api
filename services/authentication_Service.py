import xml.etree.ElementTree as ET
from odoo.http import request


class AuthenticationService:

    @staticmethod
    def get_token(api_key):
        try:
            user_id = request.env["res.users.apikeys"]._check_credentials(scope="rpc", key=api_key)
            if user_id:
                access_token_model = request.env["api.access_token"]
                token = access_token_model.find_or_create_token(user_id=user_id, create=True)
                return token
        except Exception as e:
            return None

    @staticmethod
    def extract_api_key_from_soap(xml_data):
        ns = {
            "wsse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
            "soapenv": "http://schemas.xmlsoap.org/soap/envelope/"
        }
        try:
            root = ET.fromstring(xml_data)
            password_el = root.find(".//wsse:Password", ns)
            if password_el is not None and password_el.text:
                return password_el.text.strip()
        except ET.ParseError as e:
            return None

