from odoo import http
import logging
from odoo.http import request
from odoo.addons.psn_api.services.authentication_Service import AuthenticationService
from odoo.addons.psn_api.services.xml_Parsing import XmlParsingService
from odoo.addons.psn_api.services.cus_Data_Extractor import CustomerDataExtractor
from odoo.addons.psn_api.services.room_stay_Extractor import RoomStayExtractor
from odoo.addons.psn_api.services.mainService import ReservationService
from odoo.addons.psn_api.services.responseBuilder import ResponseBuilder

_logger = logging.getLogger(__name__)


class PsnAPI(http.Controller):
    """Main API controller with dependency injection"""

    def __init__(self):
        self.auth_service = AuthenticationService()
        self.xml_service = XmlParsingService()
        self.customer_extractor = CustomerDataExtractor()
        self.room_stay_extractor = RoomStayExtractor()
        self.reservation_service = ReservationService()
        self.response_builder = ResponseBuilder()

    @http.route(["/api/test_connection"], methods=["POST"], type="http", auth="none", csrf=False)
    def get_test_connection(self, **post):
        """Main API endpoint for Siteminder reservations"""
        _logger.info("===== Siteminder API Call Received =====")

        try:
            soap_body = request.httprequest.data.decode("utf-8")
            _logger.info(f"Received XML: {soap_body[:500]}...")

            # Extract and validate API key
            api_key = self.auth_service.extract_api_key_from_soap(soap_body)
            if not api_key:
                return self.response_builder.build_error_response(
                    "Missing <wsse:Password> field in SOAP XML.",
                    "authentication_error",
                    soap_body
                )

            # Validate access token
            access_token = self.auth_service.get_token(api_key)
            if not access_token:
                return self.response_builder.build_error_response(
                    "Invalid API key.",
                    "authentication_error",
                    soap_body
                )

            _logger.info("Authentication successful - Creating manual reservation...")

            # Parse XML
            parse_data = self.xml_service.parse_hotel_reservation_xml(soap_body)
            if not parse_data:
                return self.response_builder.build_error_response(
                    "Failed to parse XML. Make sure the SOAP body is well-formed.",
                    "validation_error",
                    soap_body  # Pass raw SOAP body to try extracting EchoToken
                )

            # Extract reservation data
            try:
                hotel_reservation = self.xml_service.extract_reservation_data(parse_data)
            except Exception as e:
                return self.response_builder.build_error_response(
                    f"Failed to extract reservation data: {str(e)}",
                    "validation_error",
                    parse_data
                )

            # Extract customer and room stay information
            customer_info = self.customer_extractor.extract_customer_info(hotel_reservation)
            if not customer_info.get('name'):
                return self.response_builder.build_error_response(
                    "Missing customer name in data",
                    "validation_error",
                    parse_data
                )

            room_stay_info = self.room_stay_extractor.extract_room_stay_info(hotel_reservation)
            if not room_stay_info:
                return self.response_builder.build_error_response(
                    "No room stay information found in reservation",
                    "validation_error",
                    parse_data
                )


            warnings = []

            if not customer_info.get('email'):
                warnings.append({
                    'type': '10',
                    'code': '321',
                    'message': 'Guest email address is required'
                })
            if not customer_info.get('phone'):
                warnings.append({
                    'type': '10',
                    'code': '322',
                    'message': 'Guest phone number is recommended'
                })
            if not customer_info.get('amount_after_tax') or customer_info.get('amount_after_tax') == '0':
                warnings.append({
                    'type': '10',
                    'code': '323',
                    'message': 'Total amount information is missing'
                })

            if room_stay_info.get('adults', 0) <= 1 and room_stay_info.get('children', 0) == 0:
                warnings.append({
                    'type': '10',
                    'code': '324',
                    'message': 'Guest count information was defaulted'
                })

            room_stay_info['siteminder_id'] = customer_info.get('siteminder_id', '')
            _logger.info(room_stay_info)
            # Create reservation
            reservation_result = self.reservation_service.create_hotel_reservation(
                customer_info, room_stay_info
            )

            # Check if reservation creation was successful
            if reservation_result['success']:
                _logger.info(f"✅ Manual reservation created successfully: {reservation_result['reservation_no']}")


                if warnings:
                    _logger.info(f"⚠️ Reservation created with {len(warnings)} warnings")
                    return self.response_builder.build_success_with_warnings_response(
                        reservation_result, parse_data, warnings
                    )
                else:
                    return self.response_builder.build_success_response(reservation_result, parse_data)
            else:
                error_type = reservation_result.get('error_type', 'unknown_error')
                error_message = reservation_result.get('error', 'Unknown error occurred')

                _logger.error(f"❌ Failed to create manual reservation: {error_message}")

                return self.response_builder.build_error_response(
                    error_message,
                    error_type,
                    parse_data
                )


        except Exception as e:

            _logger.error(f"Exception in test_connection endpoint: {str(e)}")

            import traceback

            _logger.error(traceback.format_exc())

            return self.response_builder.build_error_response(

                f"An unexpected error occurred: {str(e)}",

                "system_error",

                None  # No parse_data available in this case

            )