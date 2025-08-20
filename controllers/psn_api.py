import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime


from odoo import http, fields, _
from odoo.addons.psn_api.models.common import invalid_response, valid_response
from odoo.http import request



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



    def parse_hotel_reservation_complete(self, xml_data):
        """Parse OTA Hotel Reservation XML with complete data extraction"""
        try:
            ns = {
                "soap-env": "http://schemas.xmlsoap.org/soap/envelope/",
                "ota": "http://www.opentravel.org/OTA/2003/05",
                "wsse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
            }
            root = ET.fromstring(xml_data)

            # Parse SOAP Header
            soap_header = {}
            header = root.find(".//soap-env:Header", ns)
            if header is not None:
                # Security info
                username_token = header.find(".//wsse:UsernameToken", ns)
                if username_token is not None:
                    username = username_token.find(".//wsse:Username", ns)
                    password = username_token.find(".//wsse:Password", ns)
                    soap_header["username"] = username.text if username is not None else ""
                    soap_header["password_type"] = password.get("Type") if password is not None else ""

            # Parse OTA Request Info
            ota_request = root.find(".//ota:OTA_HotelResNotifRQ", ns)
            request_info = {}
            if ota_request is not None:
                request_info["echo_token"] = ota_request.get("EchoToken")
                request_info["timestamp"] = ota_request.get("TimeStamp")
                request_info["version"] = ota_request.get("Version")

            reservations = []
            hotel_reservations = root.findall(".//ota:HotelReservation", ns)

            for hotel_res in hotel_reservations:
                reservation_data = {
                    "soap_header": soap_header,
                    "request_info": request_info
                }

                # Basic reservation info
                reservation_data["create_date"] = hotel_res.get("CreateDateTime")
                reservation_data["last_modify_date"] = hotel_res.get("LastModifyDateTime")
                reservation_data["status"] = hotel_res.get("ResStatus")

                # POS (Point of Sale) Information
                pos_info = []
                pos_sources = hotel_res.findall(".//ota:POS/ota:Source", ns)
                for source in pos_sources:
                    source_data = {}

                    # Requestor ID
                    requestor_id = source.find(".//ota:RequestorID", ns)
                    if requestor_id is not None:
                        source_data["requestor_id"] = requestor_id.get("ID")

                    # Booking Channel
                    booking_channel = source.find(".//ota:BookingChannel", ns)
                    if booking_channel is not None:
                        source_data["booking_channel_type"] = booking_channel.get("Type")
                        source_data["booking_channel_primary"] = booking_channel.get("Primary")

                        company_name = booking_channel.find(".//ota:CompanyName", ns)
                        if company_name is not None:
                            source_data["company_name"] = company_name.text

                    if source_data:
                        pos_info.append(source_data)

                reservation_data["pos_info"] = pos_info

                # Unique ID
                unique_id = hotel_res.find(".//ota:UniqueID", ns)
                if unique_id is not None:
                    reservation_data["reservation_id"] = unique_id.get("ID")
                    reservation_data["unique_id_type"] = unique_id.get("Type")

                # Room Stay Information
                room_stays = []
                room_stay_elements = hotel_res.findall(".//ota:RoomStay", ns)

                for room_stay in room_stay_elements:
                    room_stay_data = {}

                    # Room Types
                    room_types = []
                    room_type_elements = room_stay.findall(".//ota:RoomType", ns)
                    for room_type in room_type_elements:
                        room_type_data = {
                            "room_id": room_type.get("RoomID"),
                            "room_type": room_type.get("RoomType"),
                            "room_type_code": room_type.get("RoomTypeCode")
                        }

                        # Room Description
                        room_desc = room_type.find(".//ota:RoomDescription/ota:Text", ns)
                        if room_desc is not None:
                            room_type_data["description"] = room_desc.text

                        room_types.append(room_type_data)

                    room_stay_data["room_types"] = room_types

                    # Rate Plans
                    rate_plans = []
                    rate_plan_elements = room_stay.findall(".//ota:RatePlan", ns)
                    for rate_plan in rate_plan_elements:
                        rate_plan_data = {
                            "rate_plan_name": rate_plan.get("RatePlanName"),
                            "rate_plan_code": rate_plan.get("RatePlanCode"),
                            "effective_date": rate_plan.get("EffectiveDate"),
                            "expire_date": rate_plan.get("ExpireDate")
                        }

                        # Rate Plan Description
                        rate_desc = rate_plan.find(".//ota:RatePlanDescription/ota:Text", ns)
                        if rate_desc is not None:
                            rate_plan_data["description"] = rate_desc.text

                        rate_plans.append(rate_plan_data)

                    room_stay_data["rate_plans"] = rate_plans

                    # Room Rates
                    room_rates = []
                    room_rate_elements = room_stay.findall(".//ota:RoomRate", ns)
                    for room_rate in room_rate_elements:
                        room_rate_data = {
                            "effective_date": room_rate.get("EffectiveDate"),
                            "expire_date": room_rate.get("ExpireDate"),
                            "room_type_code": room_rate.get("RoomTypeCode"),
                            "rate_plan_code": room_rate.get("RatePlanCode"),
                            "room_id": room_rate.get("RoomID"),
                            "number_of_units": room_rate.get("NumberOfUnits")
                        }

                        # Rates
                        rates = []
                        rate_elements = room_rate.findall(".//ota:Rate", ns)
                        for rate in rate_elements:
                            rate_data = {
                                "unit_multiplier": rate.get("UnitMultiplier"),
                                "effective_date": rate.get("EffectiveDate"),
                                "expire_date": rate.get("ExpireDate")
                            }

                            # Base Amount
                            base = rate.find(".//ota:Base", ns)
                            if base is not None:
                                rate_data["base_amount_before_tax"] = base.get("AmountBeforeTax")
                                rate_data["base_currency"] = base.get("CurrencyCode")

                            # Total Amount (in Rate)
                            total = rate.find(".//ota:Total", ns)
                            if total is not None:
                                rate_data["total_amount_before_tax"] = total.get("AmountBeforeTax")
                                rate_data["total_currency"] = total.get("CurrencyCode")

                            rates.append(rate_data)

                        room_rate_data["rates"] = rates
                        room_rates.append(room_rate_data)

                    room_stay_data["room_rates"] = room_rates

                    # Guest Counts
                    guest_counts = []
                    guest_count_elements = room_stay.findall(".//ota:GuestCount", ns)
                    for guest_count in guest_count_elements:
                        guest_counts.append({
                            "age_qualifying_code": guest_count.get("AgeQualifyingCode"),
                            "count": int(guest_count.get("Count", 1))
                        })
                    room_stay_data["guest_counts"] = guest_counts

                    # Time Span (Room Stay)
                    time_span = room_stay.find(".//ota:TimeSpan", ns)
                    if time_span is not None:
                        room_stay_data["check_in"] = time_span.get("Start")
                        room_stay_data["check_out"] = time_span.get("End")

                    # Total (Room Stay)
                    total = room_stay.find(".//ota:Total", ns)
                    if total is not None:
                        room_stay_data["total_amount_after_tax"] = float(total.get("AmountAfterTax", 0))
                        room_stay_data["currency"] = total.get("CurrencyCode")

                    room_stays.append(room_stay_data)

                reservation_data["room_stays"] = room_stays

                # ResGlobalInfo
                res_global_info = hotel_res.find(".//ota:ResGlobalInfo", ns)
                if res_global_info is not None:
                    global_info = {}

                    # Global Time Span
                    global_time_span = res_global_info.find(".//ota:TimeSpan", ns)
                    if global_time_span is not None:
                        global_info["start_date"] = global_time_span.get("Start")
                        global_info["end_date"] = global_time_span.get("End")

                    # Global Total with Taxes
                    global_total = res_global_info.find(".//ota:Total", ns)
                    if global_total is not None:
                        global_info["total_amount_after_tax"] = float(global_total.get("AmountAfterTax", 0))
                        global_info["total_currency"] = global_total.get("CurrencyCode")

                        # Taxes
                        taxes_element = global_total.find(".//ota:Taxes", ns)
                        if taxes_element is not None:
                            taxes_info = {
                                "total_tax_amount": taxes_element.get("Amount"),
                                "tax_currency": taxes_element.get("CurrencyCode")
                            }

                            # Individual Tax Items
                            tax_items = []
                            tax_elements = taxes_element.findall(".//ota:Tax", ns)
                            for tax in tax_elements:
                                tax_data = {
                                    "amount": tax.get("Amount"),
                                    "percent": tax.get("Percent"),
                                    "currency": tax.get("CurrencyCode")
                                }

                                # Tax Description
                                tax_desc = tax.find(".//ota:TaxDescription/ota:Text", ns)
                                if tax_desc is not None:
                                    tax_data["description"] = tax_desc.text

                                tax_items.append(tax_data)

                            taxes_info["tax_items"] = tax_items
                            global_info["taxes"] = taxes_info

                    # Hotel Reservation IDs
                    reservation_ids = []
                    res_id_elements = res_global_info.findall(".//ota:HotelReservationID", ns)
                    for res_id in res_id_elements:
                        reservation_ids.append({
                            "type": res_id.get("ResID_Type"),
                            "source": res_id.get("ResID_Source"),
                            "value": res_id.get("ResID_Value")
                        })
                    global_info["reservation_ids"] = reservation_ids

                    # Basic Property Info
                    basic_property = res_global_info.find(".//ota:BasicPropertyInfo", ns)
                    if basic_property is not None:
                        global_info["hotel_code"] = basic_property.get("HotelCode")

                    # Profiles
                    profiles = []
                    profile_elements = res_global_info.findall(".//ota:Profile", ns)
                    for profile in profile_elements:
                        profile_data = {
                            "profile_type": profile.get("ProfileType")
                        }

                        # Profile Unique ID
                        profile_unique_id = profile.find("../ota:UniqueID", ns)
                        if profile_unique_id is not None:
                            profile_data["profile_id"] = profile_unique_id.get("ID")
                            profile_data["profile_id_type"] = profile_unique_id.get("Type")

                        # Customer Info
                        customer = profile.find(".//ota:Customer", ns)
                        if customer is not None:
                            customer_data = {
                                "vip_indicator": customer.get("VIP_Indicator")
                            }

                            # Person Name
                            person_name = customer.find(".//ota:PersonName", ns)
                            if person_name is not None:
                                given_name = person_name.find(".//ota:GivenName", ns)
                                surname = person_name.find(".//ota:Surname", ns)
                                customer_data["first_name"] = given_name.text if given_name is not None else ""
                                customer_data["last_name"] = surname.text if surname is not None else ""

                            # Telephone
                            telephone = customer.find(".//ota:Telephone", ns)
                            if telephone is not None:
                                customer_data["phone_tech_type"] = telephone.get("PhoneTechType")
                                customer_data["phone_number"] = telephone.get("PhoneNumber")

                            # Email
                            email = customer.find(".//ota:Email", ns)
                            if email is not None:
                                customer_data["email_type"] = email.get("EmailType")
                                customer_data["email"] = email.text

                            # Address
                            address = customer.find(".//ota:Address", ns)
                            if address is not None:
                                address_data = {
                                    "address_type": address.get("Type")
                                }

                                # Address Lines
                                address_lines = address.findall(".//ota:AddressLine", ns)
                                address_data["address_lines"] = [line.text for line in address_lines if line.text]

                                # City
                                city = address.find(".//ota:CityName", ns)
                                if city is not None:
                                    address_data["city"] = city.text

                                # Postal Code
                                postal_code = address.find(".//ota:PostalCode", ns)
                                if postal_code is not None:
                                    address_data["postal_code"] = postal_code.text

                                # State/Province
                                state = address.find(".//ota:StateProv", ns)
                                if state is not None:
                                    address_data["state"] = state.text

                                customer_data["address"] = address_data

                            profile_data["customer"] = customer_data

                        profiles.append(profile_data)

                    global_info["profiles"] = profiles

                    # Comments
                    comments = []
                    comment_elements = res_global_info.findall(".//ota:Comment", ns)
                    for comment in comment_elements:
                        text_el = comment.find(".//ota:Text", ns)
                        if text_el is not None:
                            comments.append(text_el.text)
                    global_info["comments"] = comments

                    reservation_data["global_info"] = global_info

                reservations.append(reservation_data)

            return reservations

        except Exception as e:
            _logger.error("Failed to parse hotel reservation XML: %s", e)
            return []




    def create_reservation_from_xml(self, parsed_xml_data):
        """
        Create hotel reservation from parsed XML data - Simplified version
        """
        try:
            # Get required models
            HotelReservation = request.env['hotel.reservation']
            HotelRoomType = request.env['hotel.room.type']
            HotelRoom = request.env['hotel.room']

            # Extract the first reservation from parsed data
            if not parsed_xml_data or len(parsed_xml_data) == 0:
                return {'success': False, 'error': 'No reservation data found'}

            reservation_data = parsed_xml_data[0]

            global_info = reservation_data.get('global_info', {})

            # STEP 1: Generate custom reservation number
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

            # STEP 2: Extract customer information
            customer_info = reservation_data.get('global_info', {}).get('profiles', [{}])[0].get('customer', {})
            first_name = customer_info.get('first_name', '')
            last_name = customer_info.get('last_name', '')
            customer_name = f"{first_name} {last_name}".strip()

            # Extract contact information
            email = customer_info.get('email', '')
            phone = customer_info.get('phone_number', '')

            # STEP 3: Extract dates
            # STEP 3: Extract dates from RoomStay TimeSpan
            checkin_date = None
            checkout_date = None

            room_stays = reservation_data.get('room_stays', [])
            if room_stays:
                # Get dates from the first room stay's TimeSpan
                first_room_stay = room_stays[0]
                checkin_date = first_room_stay.get('check_in', '')
                checkout_date = first_room_stay.get('check_out', '')

                print(f"🗓️ Extracted dates from RoomStay TimeSpan:")
                print(f"   Check-in: {checkin_date}")
                print(f"   Check-out: {checkout_date}")

            # Fallback to global dates if RoomStay dates are not available
            if not checkin_date or not checkout_date:
                global_info = reservation_data.get('global_info', {})
                checkin_date = checkin_date or global_info.get('start_date', '')
                checkout_date = checkout_date or global_info.get('end_date', '')
                print(f"📅 Using global dates as fallback:")
                print(f"   Check-in: {checkin_date}")
                print(f"   Check-out: {checkout_date}")

            def parse_and_format_datetime(date_string, default_time):
                """
                Parse date string and convert to proper datetime format for Odoo
                Handles various date formats like '2025-09-1', '2025-09-01', etc.
                """
                try:
                    if not date_string:
                        return None

                    # Clean the date string
                    date_string = date_string.strip()

                    # Parse the date using datetime.strptime with multiple format attempts
                    date_formats = [
                        '%Y-%m-%d',  # 2025-09-01
                        '%Y-%m-%d',  # Will also handle 2025-09-1 after padding
                        '%Y/%m/%d',  # 2025/09/01
                        '%Y/%m/%d',  # Will also handle 2025/9/1 after padding
                    ]

                    # Pad single digit months/days if needed
                    parts = date_string.replace('/', '-').split('-')
                    if len(parts) == 3:
                        year, month, day = parts
                        # Pad month and day with leading zeros if needed
                        month = month.zfill(2)
                        day = day.zfill(2)
                        normalized_date = f"{year}-{month}-{day}"
                    else:
                        normalized_date = date_string

                    # Parse the normalized date
                    parsed_date = datetime.strptime(normalized_date, '%Y-%m-%d')

                    # Combine with default time
                    datetime_str = f"{normalized_date} {default_time}"

                    # Parse to datetime object to validate
                    final_datetime = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')

                    return final_datetime

                except ValueError as e:
                    print(f"❌ Error parsing date '{date_string}': {e}")
                    return None

            # Convert dates to proper datetime format (YYYY-MM-DD HH:MM:SS)
            checkin_datetime_obj = parse_and_format_datetime(checkin_date, "14:00:00")
            checkout_datetime_obj = parse_and_format_datetime(checkout_date, "12:00:00")

            print(f"🕐 Final datetime format:")
            print(f"   Check-in datetime: {checkin_datetime_obj}")
            print(f"   Check-out datetime: {checkout_datetime_obj}")

            # Current datetime for date_order
            date_order = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


            # STEP 4: Calculate adults and children from guest counts
            adults = 0
            children = 0

            room_stays = reservation_data.get('room_stays', [])
            if room_stays:
                guest_counts = room_stays[0].get('guest_counts', [])
                for guest_count in guest_counts:
                    age_code = guest_count.get('age_qualifying_code', '')
                    count = guest_count.get('count', 0)

                    # Age qualifying codes: 10 = Adult, 8 = Child
                    if age_code in ['10', '1']:  # Adult codes
                        adults += count
                    elif age_code in ['8', '7', '2']:  # Child codes
                        children += count
                    else:
                        adults += count  # Default to adult if unknown

            # Ensure at least 1 adult
            if adults == 0:
                adults = 1

            # STEP 5: Extract comments
            comments = global_info.get('comments', [])
            customer_note = '\n'.join(comments) if comments else 'Reservation from XML'

            # STEP 6: Create reservation lines based on room types from XML
            reservation_lines = []

            if room_stays:
                room_types_xml = room_stays[0].get('room_types', [])

                for room_type_xml in room_types_xml:
                    room_type_code = room_type_xml.get('room_type_code', '')
                    room_type_name = room_type_xml.get('room_type', '')

                    print(f"🏨 Processing room type code: {room_type_code} ({room_type_name})")

                    room_type_odoo=HotelRoomType.sudo().search([
                        ('name','=',room_type_name)
                    ],limit=1)
                    print(f"OK: {room_type_odoo} ({room_type_name})")

                    # Find room directly by name using RoomTypeCode
                    room_odoo = HotelRoom.sudo().search([
                        ('name', '=', room_type_code)
                    ], limit=1)

                    print(f"OK: {room_odoo} ({room_type_code})")

                    # Create reservation line if room found
                    if room_odoo and room_type_odoo:
                        reservation_lines.append((0, 0, {
                            'categ_id': room_type_odoo.id,  # Get room type from the room itself
                            'reserve': [(6, 0, [room_odoo.id])],
                        }))
                        print(f"✅ Added reservation line: {room_odoo.name}")



            # STEP 7: Create reservation
            reservation_vals = {
                'date_order': date_order,
                'company_id': 1,
                'partner_id': 149,
                'customer_name': customer_name,
                'customer_note': customer_note,
                'reservation_referent': 'other',  # Keep simple
                'pricelist_id': 1,
                'partner_invoice_id': 149,
                'partner_order_id': 149,
                'partner_shipping_id': 149,
                'checkin': fields.Datetime.from_string(checkin_datetime_obj),
                'checkout': fields.Datetime.from_string(checkout_datetime_obj),
                'adults': adults,
                'children': children,
                'state': 'draft',
                'payment': 'not_paid',
                'email': email,
                'ph_no': phone,
                'reservation_line': reservation_lines
            }

            # Create the reservation
            new_reservation = HotelReservation.sudo().create(reservation_vals)
            print(f"📝 Created reservation with ID: {new_reservation.id}")

            # Update with custom reservation number
            new_reservation.sudo().write({
                'reservation_no': new_reservation_no
            })

            # Refresh the record
            new_reservation.sudo().invalidate_cache()
            updated_reservation = HotelReservation.sudo().browse(new_reservation.id)

            print(f"✅ Updated reservation number to: {updated_reservation.reservation_no}")

            return {
                'success': True,
                'reservation_id': updated_reservation.id,
                'reservation_no': updated_reservation.reservation_no,
                'customer_name': customer_name,
                'checkin': checkin_date,
                'checkout': checkout_date,
                'adults': adults,
                'children': children,
                'message': f'Reservation created successfully'
            }

        except Exception as e:
            print(f"❌ Error creating reservation: {str(e)}")
            return {
                'success': False,
                'error': f'Error: {str(e)}'
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

            parse_data=self.parse_hotel_reservation_complete(soap_body)
            reservation_result = self.create_reservation_from_xml(parse_data)
            if reservation_result['success']:
                _logger.info(f"✅ Manual reservation created successfully: {reservation_result['reservation_no']}")

                # Return success response with reservation details
                response_data = {
                    "status": "success",
                    "message": "Manual reservation created successfully",
                    "reservation_data": reservation_result,
                    "timestamp": fields.Datetime.now().isoformat(),
                    "Real Soap Body":parse_data
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
