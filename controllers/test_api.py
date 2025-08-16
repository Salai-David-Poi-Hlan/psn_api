import json
import logging
import werkzeug.wrappers
import xml.etree.ElementTree as ET

from odoo import http
from odoo.addons.psn_api.models.common import invalid_response, valid_response
from odoo.http import request

_logger = logging.getLogger(__name__)


class PsnAPI(http.Controller):

    # ===== GET Token =====
    def get_token(self, api_key):
        user_id = request.env["res.users.apikeys"]._check_credentials(scope="rpc", key=api_key)
        if user_id:
            access_token = request.env["api.access_token"].find_or_create_token(user_id=user_id, create=True)
        else:
            access_token = None
        return access_token

    # ===== Extract API Key from SOAP XML =====
    def extract_api_key_from_soap(self, xml_data):
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

    # ===== GET Test Connection =====
    @http.route(["/api/test_connection"], methods=["POST"], type="http", auth="none", csrf=False)
    def get_test_connection(self, **post):
        print("===== get_test_connection =====")
        soap_body = request.httprequest.data.decode("utf-8")
        api_key = self.extract_api_key_from_soap(soap_body)

        # ===== Check API Key =====
        if api_key:
            access_token = self.get_token(api_key)
        else:
            return invalid_response(
                "Missing Error!",
                "Missing <wsse:Password> field in SOAP XML.",
                403,
            )

        # ===== Check Access Token =====
        if not access_token:
            return invalid_response(
                "Key Error!",
                "Authentication failed.",
                401,
            )

        return werkzeug.wrappers.Response(
            status=200,
            content_type="application/json; charset=utf-8",
            headers=[("Cache-Control", "no-store"), ("Pragma", "no-cache")],
            response=json.dumps({
                "odoo": "Connection Successful."
            }),
        )

   # @http.route(["http://localhost:8069/api/test_connection"], methods=["GET"], type="http", auth="none", csrf=False)
   # def simple_test(self):
       # return "Hello World"
