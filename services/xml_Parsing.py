import logging
import json
import xmltodict
_logger = logging.getLogger(__name__)

class XmlParsingService:
    """Service for handling XML parsing operations"""

    @staticmethod
    def parse_hotel_reservation_xml(xml_data):
        """Convert XML to dictionary"""
        try:
            xml_dict = xmltodict.parse(xml_data)
            _logger.info("Full XML converted to dict: %s", json.dumps(xml_dict, indent=2, default=str)[:2000])
            return xml_dict
        except Exception as e:
            _logger.error("Failed to parse XML: %s", e)
            return {}

    @staticmethod
    def extract_reservation_data(xml_dict):
        """Extract reservation data from XML dictionary"""
        try:
            # Navigate the XML structure
            soap_envelope = xml_dict.get('soap-env:Envelope', {})
            soap_body = soap_envelope.get('soap-env:Body', {})
            ota_request = soap_body.get('OTA_HotelResNotifRQ', {})

            if not ota_request:
                raise ValueError("No OTA_HotelResNotifRQ found in XML")

            hotel_reservations_container = ota_request.get('HotelReservations', {})
            hotel_reservations = hotel_reservations_container.get('HotelReservation', [])

            if not isinstance(hotel_reservations, list):
                hotel_reservations = [hotel_reservations]

            if not hotel_reservations:
                raise ValueError("No hotel reservations found in XML")

            return hotel_reservations[0]

        except Exception as e:
            _logger.error(f"Error extracting reservation data: {e}")
            raise