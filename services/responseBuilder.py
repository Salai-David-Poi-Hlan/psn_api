import uuid
from datetime import datetime
from odoo import fields
from odoo.http import request
import xml.etree.ElementTree as ET


class ResponseBuilder:

    @staticmethod
    def extract_echo_token(parse_data):
        """Extract EchoToken from the original SOAP request"""
        try:
            # Try to find EchoToken in the parsed data
            if isinstance(parse_data, dict):
                # Look for EchoToken in various possible locations
                echo_token = parse_data.get('EchoToken')
                if echo_token:
                    return echo_token

                # Check nested structures
                for key, value in parse_data.items():
                    if isinstance(value, dict) and 'EchoToken' in value:
                        return value['EchoToken']

            # If parse_data is XML string, parse it to find EchoToken
            if isinstance(parse_data, str):
                root = ET.fromstring(parse_data)
                # Look for EchoToken attribute in any element
                for elem in root.iter():
                    echo_token = elem.get('EchoToken')
                    if echo_token:
                        return echo_token

            # Generate fallback UUID if not found
            return str(uuid.uuid4())

        except Exception:
            # Fallback to generated UUID if extraction fails
            return str(uuid.uuid4())

    @staticmethod
    def build_success_response(reservation_result, parse_data):
        """Build OTA XML success response for hotel reservation"""

        echo_token = ResponseBuilder.extract_echo_token(parse_data)
        current_timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        reservation_no = reservation_result.get('reservation_no', '')

        # Build OTA XML response
        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
    <SOAP-ENV:Body>
        <OTA_HotelResNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"
             Version="1.0" TimeStamp="{current_timestamp}" EchoToken="{echo_token}">
            <Success/>
            <HotelReservations>
                <HotelReservation>
                    <UniqueID ID="{reservation_no}"/>
                    <ResGlobalInfo>
                        <HotelReservationIDs>
                            <HotelReservationID ResID_Type="10"
                                 ResID_Value="{reservation_no}"/>
                        </HotelReservationIDs>
                    </ResGlobalInfo>
                </HotelReservation>
            </HotelReservations>
        </OTA_HotelResNotifRS>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""

        return request.make_response(
            xml_response,
            headers=[
                ('Content-Type', 'text/xml; charset=utf-8'),
                ('Access-Control-Allow-Origin', '*')
            ]
        )

    @staticmethod
    def build_success_with_warnings_response(reservation_result, parse_data, warnings):
        """Build OTA XML success response with warnings for hotel reservation"""

        echo_token = ResponseBuilder.extract_echo_token(parse_data)
        current_timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        reservation_no = reservation_result.get('reservation_no', '')

        # Build warnings XML
        warnings_xml = ""
        if warnings:
            warnings_xml = "\n            <Warnings>"
            for warning in warnings:
                warnings_xml += f'\n                <Warning Type="{warning["type"]}" Code="{warning["code"]}">{warning["message"]}</Warning>'
            warnings_xml += "\n            </Warnings>"

        # Build OTA XML response with warnings
        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
    <SOAP-ENV:Body>
        <OTA_HotelResNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"
             Version="1.0" TimeStamp="{current_timestamp}" EchoToken="{echo_token}">
            <Success/>{warnings_xml}
            <HotelReservations>
                <HotelReservation>
                    <UniqueID ID="{reservation_no}"/>
                    <ResGlobalInfo>
                        <HotelReservationIDs>
                            <HotelReservationID ResID_Type="10"
                                 ResID_Value="{reservation_no}"/>
                        </HotelReservationIDs>
                    </ResGlobalInfo>
                </HotelReservation>
            </HotelReservations>
        </OTA_HotelResNotifRS>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""

        return request.make_response(
            xml_response,
            headers=[
                ('Content-Type', 'text/xml; charset=utf-8'),
                ('Access-Control-Allow-Origin', '*')
            ]
        )




    @staticmethod
    def build_error_response(error_message, error_type="system_error", parse_data=None):
        """Build OTA XML error response for hotel reservation"""

        echo_token = ResponseBuilder.extract_echo_token(parse_data) if parse_data else str(uuid.uuid4())
        current_timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        # Map error types to OTA error codes
        error_mapping = {
            'validation_error': {'Type': '4', 'Code': '400'},  # Business rule validation error
            'capacity_error': {'Type': '6', 'Code': '392'},  # No availability
            'system_error': {'Type': '1', 'Code': '500'},  # System/processing error
            'reservation_error': {'Type': '3', 'Code': '300'},  # Application error
            'confirmation_error': {'Type': '3', 'Code': '301'},  # Application error - confirmation failed
            'authentication_error': {'Type': '6', 'Code': '497'},  # Authentication failed
            'unknown_error': {'Type': '1', 'Code': '500'}  # Default to system error
        }

        error_info = error_mapping.get(error_type, error_mapping['unknown_error'])

        # Build OTA XML error response
        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
    <SOAP-ENV:Body>
        <OTA_HotelResNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"
             Version="1.0" TimeStamp="{current_timestamp}" EchoToken="{echo_token}">
            <Errors>
                <Error Type="{error_info['Type']}" Code="{error_info['Code']}">{error_message}</Error>
            </Errors>
        </OTA_HotelResNotifRS>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""

        response = request.make_response(
            xml_response,
            headers=[
                ('Content-Type', 'text/xml; charset=utf-8'),
                ('Access-Control-Allow-Origin', '*')
            ]
        )
        response.status_code = 200  # Siteminder expects 200 even for errors
        return response




    @staticmethod
    def build_authentication_error_response(error_message):
        """Build simple XML error response for authentication failures"""
        current_timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        fallback_token = str(uuid.uuid4())

        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
    <SOAP-ENV:Body>
        <OTA_HotelResNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"
             Version="1.0" TimeStamp="{current_timestamp}" EchoToken="{fallback_token}">
            <Errors>
                <Error Type="1" Code="401">{error_message}</Error>
            </Errors>
        </OTA_HotelResNotifRS>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""

        return request.make_response(
            xml_response,
            status=200,
            headers=[
                ('Content-Type', 'text/xml; charset=utf-8'),
                ('Access-Control-Allow-Origin', '*')
            ]
        )