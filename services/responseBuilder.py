import json
from odoo import fields
from odoo.http import  request

class ResponseBuilder:
    """Service for building HTTP responses"""

    @staticmethod
    def build_success_response(reservation_result, parse_data):
        """Build success response"""
        response_data = {
            "status": "success",
            "message": "Manual reservation created successfully",
            "reservation_data": reservation_result,
            "timestamp": fields.Datetime.now().isoformat(),
            "Real Soap Body": parse_data
        }

        return request.make_response(
            json.dumps(response_data, indent=2, default=str),
            headers=[
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*')
            ]
        )

    @staticmethod
    def build_error_response(error_message, status_code=500):
        """Build error response"""
        error_response = {
            "status": "error",
            "message": error_message,
            "timestamp": fields.Datetime.now().isoformat()
        }

        return request.make_response(
            json.dumps(error_response, indent=2, default=str),
            status=status_code,
            headers=[
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*')
            ]
        )