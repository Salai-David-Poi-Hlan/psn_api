import xmltodict


class XmlParsingService:


    @staticmethod
    def parse_hotel_reservation_xml(xml_data):

        try:
            xml_dict = xmltodict.parse(xml_data)

            return xml_dict
        except Exception as e:

            return {}

    @staticmethod
    def extract_reservation_data(xml_dict):

        try:

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

            raise