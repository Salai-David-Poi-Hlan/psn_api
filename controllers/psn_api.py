from odoo import http
import logging
from odoo.http import request
from odoo.addons.psn_api.models.common import invalid_response, valid_response
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
                return invalid_response(
                    "Authentication Error",
                    "Missing <wsse:Password> field in SOAP XML.",
                    403,
                )

            # Validate access token
            access_token = self.auth_service.get_token(api_key)
            if not access_token:
                return invalid_response(
                    "Authentication Error",
                    "Invalid API key.",
                    401,
                )

            _logger.info("Authentication successful - Creating manual reservation...")

            # Parse XML
            parse_data = self.xml_service.parse_hotel_reservation_xml(soap_body)
            if not parse_data:
                return invalid_response(
                    "Invalid XML",
                    "Failed to parse XML. Make sure the SOAP body is well-formed.",
                    400
                )

            # Extract reservation data
            try:
                hotel_reservation = self.xml_service.extract_reservation_data(parse_data)
            except Exception as e:
                return invalid_response(
                    "Reservation Parsing Error",
                    f"Failed to extract reservation data: {str(e)}",
                    400
                )

            # Extract customer and room stay information
            customer_info = self.customer_extractor.extract_customer_info(hotel_reservation)
            if not customer_info.get('name'):
                return invalid_response("Missing customer name in data")

            room_stay_info = self.room_stay_extractor.extract_room_stay_info(hotel_reservation)

            if not room_stay_info:
                return invalid_response(
                    "No room stay information found in reservation"
                )

            # Create reservation
            reservation_result = self.reservation_service.create_hotel_reservation(
                customer_info, room_stay_info
            )

            # Check if reservation creation was successful
            if reservation_result['success']:
                _logger.info(f"✅ Manual reservation created successfully: {reservation_result['reservation_no']}")
                return self.response_builder.build_success_response(reservation_result, parse_data)
            else:
                # Handle different types of errors from reservation service
                error_type = reservation_result.get('error_type', 'unknown_error')
                error_message = reservation_result.get('error', 'Unknown error occurred')

                _logger.error(f"❌ Failed to create manual reservation: {error_message}")

                if error_type == 'validation_error':
                    # Return validation error immediately (room not found, etc.)
                    return invalid_response(
                        "Validation Error",
                        error_message,
                        400
                    )
                elif error_type == 'system_error':
                    # Return system error
                    return invalid_response(
                        "System Error",
                        error_message,
                        500
                    )
                else:
                    # Generic error response
                    return invalid_response(
                        "Reservation Error",
                        error_message,
                        400
                    )

        except Exception as e:
            _logger.error(f"Exception in test_connection endpoint: {str(e)}")
            import traceback
            _logger.error(traceback.format_exc())
            return invalid_response(
                "Internal Server Error",
                f"An unexpected error occurred: {str(e)}",
                500
            )