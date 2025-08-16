import json
import logging
import werkzeug.wrappers
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta


from odoo import http, fields, _
from odoo.addons.psn_api.models.common import invalid_response, valid_response
from odoo.http import request
from odoo.fields import  Datetime
_logger = logging.getLogger(__name__)


class PsnAPI(http.Controller):

    def get_token(self, api_key):
        """Authenticate and get access token"""
        try:
            user_id = request.env["res.users.apikeys"]._check_credentials(scope="rpc", key=api_key)
            if user_id:
                access_token = request.env["api.access_token"].find_or_create_token(user_id=user_id, create=True)
                return access_token
        except Exception as e:
            _logger.error("Authentication error: %s", e)
        return None

    def extract_api_key_from_soap(self, xml_data):
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

    def parse_hotel_reservation(self, xml_data):
        """Parse OTA Hotel Reservation XML with corrected structure"""
        try:
            ns = {
                "soap-env": "http://schemas.xmlsoap.org/soap/envelope/",
                "ota": "http://www.opentravel.org/OTA/2003/05"
            }
            root = ET.fromstring(xml_data)

            reservations = []
            hotel_reservations = root.findall(".//ota:HotelReservation", ns)

            for hotel_res in hotel_reservations:
                reservation_data = {}

                # Basic reservation info
                reservation_data["create_date"] = hotel_res.get("CreateDateTime")
                reservation_data["last_modify_date"] = hotel_res.get("LastModifyDateTime")
                reservation_data["status"] = hotel_res.get("ResStatus")

                # Unique ID
                unique_id = hotel_res.find(".//ota:UniqueID", ns)
                if unique_id is not None:
                    reservation_data["reservation_id"] = unique_id.get("ID")

                # Hotel Code (from ResGlobalInfo)
                basic_property = hotel_res.find(".//ota:BasicPropertyInfo", ns)
                if basic_property is not None:
                    reservation_data["hotel_code"] = basic_property.get("HotelCode")

                # Room Stay Information
                room_stay = hotel_res.find(".//ota:RoomStay", ns)
                if room_stay is not None:
                    # Room Type
                    room_type = room_stay.find(".//ota:RoomType", ns)
                    if room_type is not None:
                        reservation_data["room_id"] = room_type.get("RoomID")
                        reservation_data["room_type"] = room_type.get("RoomType")
                        reservation_data["room_type_code"] = room_type.get("RoomTypeCode")

                    # Rate Plan
                    rate_plan = room_stay.find(".//ota:RatePlan", ns)
                    if rate_plan is not None:
                        reservation_data["rate_plan_name"] = rate_plan.get("RatePlanName")
                        reservation_data["rate_plan_code"] = rate_plan.get("RatePlanCode")

                    # Dates
                    time_span = room_stay.find(".//ota:TimeSpan", ns)
                    if time_span is not None:
                        reservation_data["check_in"] = time_span.get("Start")
                        reservation_data["check_out"] = time_span.get("End")

                    # Guest Count
                    guest_count = room_stay.find(".//ota:GuestCount", ns)
                    if guest_count is not None:
                        reservation_data["guest_count"] = int(guest_count.get("Count", 1))

                    # Total Amount
                    total = room_stay.find(".//ota:Total", ns)
                    if total is not None:
                        reservation_data["total_amount"] = float(total.get("AmountAfterTax", 0))
                        reservation_data["currency"] = total.get("CurrencyCode")

                # Comments from ResGlobalInfo
                comments = []
                comment_elements = hotel_res.findall(".//ota:Comment", ns)
                for comment in comment_elements:
                    text_el = comment.find(".//ota:Text", ns)
                    if text_el is not None:
                        comments.append(text_el.text)
                reservation_data["comments"] = comments

                # Booking Channel
                booking_channel = hotel_res.find(".//ota:BookingChannel", ns)
                if booking_channel is not None:
                    company_name = booking_channel.find(".//ota:CompanyName", ns)
                    if company_name is not None:
                        reservation_data["booking_channel"] = company_name.text

                # Guest Information from Profiles (corrected path)
                customer = hotel_res.find(".//ota:Profiles/ota:ProfileInfo/ota:Profile/ota:Customer", ns)
                if customer is not None:
                    person_name = customer.find(".//ota:PersonName", ns)
                    if person_name is not None:
                        given_name = person_name.find(".//ota:GivenName", ns)
                        surname = person_name.find(".//ota:Surname", ns)
                        reservation_data["guest_first_name"] = given_name.text if given_name is not None else ""
                        reservation_data["guest_last_name"] = surname.text if surname is not None else ""

                    # Contact Info
                    telephone = customer.find(".//ota:Telephone", ns)
                    if telephone is not None:
                        reservation_data["guest_phone"] = telephone.get("PhoneNumber")

                    email = customer.find(".//ota:Email", ns)
                    if email is not None:
                        reservation_data["guest_email"] = email.text

                    address = customer.find(".//ota:Address", ns)
                    if address is not None:
                        city = address.find(".//ota:CityName", ns)
                        if city is not None:
                            reservation_data["guest_city"] = city.text

                reservations.append(reservation_data)

            return reservations

        except Exception as e:
            _logger.error("Failed to parse hotel reservation XML: %s", e)
            return []

    def map_room_type(self, xml_room_type):
        """Map Siteminder room types to Odoo room types"""
        room_type_mapping = {
            'Double Room': 1,  # Standard
            'Single Room': 1,  # Standard
            'Standard Room': 1,  # Standard
            'Mini Standard': 2,  # Mini Standard
            'Deluxe Room': 3,  # Deluxe
            'Deluxe': 3,  # Deluxe
            'Superior Room': 1,  # Standard (fallback)
        }

        # Try exact match first
        if xml_room_type in room_type_mapping:
            return room_type_mapping[xml_room_type]

        # Try partial matching
        xml_room_lower = xml_room_type.lower()
        if 'deluxe' in xml_room_lower:
            return 3  # Deluxe
        elif 'mini' in xml_room_lower:
            return 2  # Mini Standard
        else:
            return 1  # Standard (default)

    def get_or_create_partner_by_booking_channel(self, booking_channel):
        """Get or create partner based on booking channel"""
        try:
            Partner = request.env['res.partner']

            # Booking channel mapping
            channel_mapping = {
                'Direct': 'Direct Booking',
                'Booking.com': 'Booking',
                'Agoda': 'Agoda',
                'Expedia': 'Expedia',
                'Trip.com': 'Trip',
                'Traveloka': 'Traveloka',
                'Siteminder': 'Siteminder'
            }

            partner_name = channel_mapping.get(booking_channel, booking_channel or 'Online Booking')

            # Try to find existing partner
            existing_partner = Partner.search([('name', '=', partner_name)], limit=1)
            if existing_partner:
                return existing_partner.id

            # Create new partner if not found
            partner_vals = {
                'name': partner_name,
                'is_company': True,
                'supplier_rank': 1,
                'customer_rank': 1,
            }
            new_partner = Partner.create(partner_vals)
            return new_partner.id

        except Exception as e:
            _logger.error(f"Error getting/creating partner: {e}")
            # Return a default partner ID or create a generic one
            return 1  # Fallback to default partner

    def generate_next_reservation_number(self):
        HotelReservation=request.env['hotel.reservation']
        last_reservation=HotelReservation.sudo().search([
            ('rservation_no','like','R/')
        ],order='reservation_no desc',limit=1)
        if last_reservation:
            last_number=last_reservation.reservation_no
            print(f"Last rservation found: {last_number}")

            if '/' in last_number:
                number_part=last_number.split('/')[-1]
                try:
                    next_number=int(number_part)+1
                    new_rservation_no=f"R/{next_number:0.5d}"
                    print(f"Generated new number: {new_rservation_no}")
                    return  new_rservation_no
                except ValueError:
                    print(f"Could not parse number from :{number_part}")
                    return  "New"
            else:
                return  "New"
        else:
            print("No previous reservation found")
            return  "New"

    def create_manual_reservation(self):
        """
        Create manual hotel reservation with specified data
        """

        # Get required models
        try:
            # Get models
            HotelReservation = request.env['hotel.reservation']
            HotelRoomType = request.env['hotel.room.type']
            HotelRoom = request.env['hotel.room']

            # Find room and room type
            standard_room_type = HotelRoomType.sudo().search([('name', '=', 'Standard')], limit=1)
            room_s404 = HotelRoom.sudo().search([('name', '=', 'S404')], limit=1)

            if not standard_room_type or not room_s404:
                return {'success': False, 'error': 'Room or room type not found'}

            # GENERATE CUSTOM NUMBER
            all_reservations = HotelReservation.sudo().search([
                ('reservation_no', 'like', 'R/')
            ])

            highest_number = 0
            for reservation in all_reservations:
                try:
                    if '/' in reservation.reservation_no:
                        number_str = reservation.reservation_no.split('/')[-1]
                        number = int(number_str)
                        if number > highest_number:
                            highest_number = number
                except:
                    continue

            next_number = highest_number + 1
            new_reservation_no = f"R/{next_number:05d}"
            print(f"🎯 Generated reservation number: {new_reservation_no}")

            # STEP 1: Create reservation WITHOUT reservation_no (let model set it to "New")
            reservation_vals = {
                # DON'T include 'reservation_no' here - let the model handle it first
                'date_order': '2025-08-15 13:22:08',
                'company_id': 1,
                'partner_id': 149,
                'customer_name': 'Manual Test Reservation V3',
                'customer_note': 'Manual reservation with post-creation number fix',
                'reservation_referent': 'other',
                'pricelist_id': 1,
                'partner_invoice_id': 149,
                'partner_order_id': 149,
                'partner_shipping_id': 149,
                'checkin': fields.Datetime.from_string('2025-09-01 13:22:31'),
                'checkout': fields.Datetime.from_string('2025-09-02 13:22:31'),
                'adults': 2,
                'children': 0,
                'state': 'draft',
                'reservation_line': [(0, 0, {
                    'categ_id': standard_room_type.id,
                    'reserve': [(6, 0, [room_s404.id])],
                })]
            }

            # Create the reservation (will get "New" from broken sequence)
            new_reservation = HotelReservation.sudo().create(reservation_vals)
            print(f"📝 Created reservation with ID: {new_reservation.id}, Number: {new_reservation.reservation_no}")

            # STEP 2: Immediately UPDATE the reservation number to our custom one
            new_reservation.sudo().write({
                'reservation_no': new_reservation_no
            })

            # Refresh the record to get updated data
            new_reservation.sudo().invalidate_cache()
            updated_reservation = HotelReservation.sudo().browse(new_reservation.id)

            print(f"✅ Updated reservation number to: {updated_reservation.reservation_no}")

            return {
                'success': True,
                'reservation_id': updated_reservation.id,
                'reservation_no': updated_reservation.reservation_no,
                'message': f'Reservation created and updated with number: {new_reservation_no}',
                'highest_found': highest_number,
                'generated_number': next_number,
                'debug': {
                    'original_number': new_reservation.reservation_no,
                    'updated_number': updated_reservation.reservation_no,
                    'step1': 'Created with model default',
                    'step2': 'Updated with custom number'
                }
            }

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return {
                'success': False,
                'error': f'Error: {str(e)}'
            }

    def verify_prerequisites(self):
        """
        Verify that all required data exists before creating reservation
        """

        checks = {
            'partner_149': False,
            'company_1': False,
            'pricelist_1': False,
            'standard_room_type': False,
            'room_s401': False
        }

        # Check partner
        partner = request.env['res.partner'].sudo().browse(149)
        if partner.exists():
            checks['partner_149'] = partner.name

        # Check company
        company = request.env['res.company'].sudo().browse(1)
        if company.exists():
            checks['company_1'] = company.name

        # Check pricelist
        pricelist = request.env['product.pricelist'].sudo().browse(1)
        if pricelist.exists():
            checks['pricelist_1'] = pricelist.name

        # Check Standard room type
        room_type = request.env['hotel.room.type'].sudo().search([('name', '=', 'Standard')], limit=1)
        if room_type:
            checks['standard_room_type'] = f"ID: {room_type.id}, Name: {room_type.name}"

        # Check room S401
        room = request.env['hotel.room'].sudo().search([('name', '=', 'S401')], limit=1)
        if room:
            checks[
                'room_s401'] = f"ID: {room.id}, Name: {room.name}, Capacity: {room.capacity}, Type: {room.room_categ_id.name}"

        return checks

    def create_missing_data_if_needed(self):
        """
        Create missing Standard room type and S401 room if they don't exist
        """
        results = []

        # Create Standard room type if missing
        standard_type = request.env['hotel.room.type'].sudo().search([('name', '=', 'Standard')], limit=1)
        if not standard_type:
            # You might need to check what fields are required for hotel.room.type
            standard_type = request.env['hotel.room.type'].sudo().create({
                'name': 'Standard',
                # Add other required fields based on your room type model
            })
            results.append(f"Created Standard room type with ID: {standard_type.id}")

        # Create room S401 if missing
        room_s401 = request.env['hotel.room'].sudo().search([('name', '=', 'S401')], limit=1)
        if not room_s401:
            # Create S401 room - you'll need to adjust fields based on your room model
            room_s401 = request.env['hotel.room'].sudo().create({
                'name': 'S401',
                'room_categ_id': standard_type.id,
                'capacity': 2,
                'status': 'available',
                'isroom': True,
                # Add product_id if required - you might need to create a product first
                # 'product_id': 1,  # Adjust based on your setup
            })
            results.append(f"Created room S401 with ID: {room_s401.id}")

        return results
    def create_hotel_reservation_with_workflow(self, reservation_data):
        """Simplified: Create hotel reservation assuming valid and complete input"""

        # Get models
        HotelReservation = request.env['hotel.reservation']
        HotelReservationLine = request.env['hotel.reservation.line']
        HotelRoomReservationLine = request.env['hotel.room.reservation.line']
        #HotelRoom = request.env['hotel.room']

        # Parse check-in and check-out dates (ISO format expected)
        checkin_date = datetime.fromisoformat(reservation_data['check_in'].replace('Z', '+00:00'))
        checkout_date = datetime.fromisoformat(reservation_data['check_out'].replace('Z', '+00:00'))

        # Extract values directly
        company_id = int(reservation_data['hotel_code'])
        #partner_id = self.get_or_create_partner_by_booking_channel(reservation_data['booking_channel'])
        room_type_id = self.map_room_type(reservation_data['room_type'])

        customer_name = f"{reservation_data['guest_first_name']} {reservation_data['guest_last_name']}"

        # Create hotel.reservation
        reservation_vals = {
            'date_order': datetime.now(),
            'company_id': 1,
            'partner_id': 193,
            'customer_name': customer_name,
            'customer_note': 'Test Customer Note',
            'reservation_referent': 'siteminder',
            'pricelist_id': 1,
            'partner_invoice_id': 193,
            'partner_order_id': 193,
            'partner_shipping_id': 193,
            'checkin': "2025-08-30 10:54:03",
            'checkout': "2025-08-31 10:54:11",
            'adults': 2,
            'children': 0,
            'state': 'draft',
            'email': reservation_data['guest_email'],
            'ph_no': reservation_data['guest_phone'],
            'country': "TH",
            'payment': 'paid',
            'room_price_summary': 0,
        }

        new_reservation = HotelReservation.sudo().create(reservation_vals)

        # Find an available room
       # room = HotelRoom.sudo().search([
           # ('room_categ_id', '=', room_type_id),
          #  ('status', '=', 'available'),
        #], limit=1)[0]

        # Create reservation line
        room = request.env['hotel.room'].sudo().create({
            'name': 'Mock Room 406',
            'room_categ_id': room_type_id,
            'capacity': 2,
            'status': 'available',
            'isroom': True,
            'product_id': 1,  # Must exist
        })

        reservation_line = HotelReservationLine.sudo().create({
            'line_id': new_reservation.id,
            'categ_id': room.room_categ_id.id,
            'reserve': [(6, 0, [room.id])],  # this line satisfies the validator
        })

        #reservation_line.write({'reserve': [(6, 0, [room.id])]})

        # Create room reservation line
        HotelRoomReservationLine.sudo().create({
            'room_id': room.id,
            'check_in': "2025-08-30 10:54:03",
            'check_out': "2025-08-31 10:54:11",
            'state': 'assigned',
            'reservation_id': new_reservation.id,
        })

        # Mark room as occupied


        # Assign mock room number and update reservation
        #room_no = f"S{room.id + 300}"
        new_reservation.write({'room_no': "S406"})

        # Confirm reservation
        new_reservation.confirmed_reservation()

        # Return result
        return {
            'success': True,
            'reservation_id': new_reservation.id,
            'reservation_no': new_reservation.reservation_no,
            'customer_name': customer_name,
            'room_assigned': True,
            #'assigned_room': room.product_id.name,
            'room_no': "S406",
            'xml_room_type': reservation_data['room_type'],
            'mapped_room_type_id': room_type_id,
            'final_state': new_reservation.state,

            'company_id': company_id,
            'checkin': checkin_date.isoformat(),
            'checkout': checkout_date.isoformat(),
            'total_amount': reservation_data['total_amount'],
            'booking_channel': reservation_data['booking_channel'],
            'status': 'success'
        }

    @http.route(["/api/test_connection"], methods=["POST"], type="http", auth="none", csrf=False)
    def get_test_connection(self, **post):
        """Main API endpoint for Siteminder reservations"""
        _logger.info("===== Siteminder API Call Received =====")

        try:
            soap_body = request.httprequest.data.decode("utf-8")
            _logger.info(f"Received XML: {soap_body[:500]}...")

            # Extract and validate API key
            api_key = self.extract_api_key_from_soap(soap_body)
            if not api_key:
                return invalid_response(
                    "Authentication Error",
                    "Missing <wsse:Password> field in SOAP XML.",
                    403,
                )

            # Validate access token
            access_token = self.get_token(api_key)
            if not access_token:
                return invalid_response(
                    "Authentication Error",
                    "Invalid API key.",
                    401,
                )

            _logger.info("Authentication successful - Creating manual reservation...")
            reservation_result = self.create_manual_reservation()

            if reservation_result['success']:
                _logger.info(f"✅ Manual reservation created successfully: {reservation_result['reservation_no']}")

                # Return success response with reservation details
                response_data = {
                    "status": "success",
                    "message": "Manual reservation created successfully",
                    "reservation_data": reservation_result,
                    "timestamp": fields.Datetime.now().isoformat()
                }

                return request.make_response(
                    json.dumps(response_data, indent=2, default=str),
                    headers=[
                        ('Content-Type', 'application/json'),
                        ('Access-Control-Allow-Origin', '*')
                    ]
                )
            else:
                _logger.error(f"❌ Failed to create manual reservation: {reservation_result['error']}")

                # Return error response
                error_response = {
                    "status": "error",
                    "message": "Failed to create manual reservation",
                    "error": reservation_result['error'],
                    "timestamp": fields.Datetime.now().isoformat()
                }

                return request.make_response(
                    json.dumps(error_response, indent=2, default=str),
                    status=500,
                    headers=[
                        ('Content-Type', 'application/json'),
                        ('Access-Control-Allow-Origin', '*')
                    ]
                )

        except Exception as e:
            _logger.error(f"Exception in test_connection endpoint: {str(e)}")

            error_response = {
                "status": "error",
                "message": "Internal server error",
                "error": str(e),
                "timestamp": fields.Datetime.now().isoformat()
            }

            return request.make_response(
                json.dumps(error_response, indent=2, default=str),
                status=500,
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*')
                ]
            )
