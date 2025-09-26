from odoo.http import request
from .dataTime_Service import  DateTimeHelper
from .reservation_No import  ReservationNumberGenerator
from datetime import  datetime
from odoo import  fields
import logging





class ReservationService:


    def __init__(self):
        self.datetime_helper = DateTimeHelper()
        self.reservation_number_generator = ReservationNumberGenerator()

    def find_reservation_by_siteminder_id(self, siteminder_id):

        try:
            hotelReservation = request.env['hotel.reservation']
            reservation = hotelReservation.sudo().search([
                ('siteminder_id', '=', siteminder_id)
            ], limit=1)
            return reservation if reservation else None
        except Exception as e:
            return None

    def create_reservation_lines(self, room_types, room_price_summary=None):

        hotelRoomType = request.env['hotel.room.type']
        hotelRoom = request.env['hotel.room']

        reservation_lines = []

        for index, room_type_data in enumerate(room_types):
            room_type_code = room_type_data.get('room_id', '')
            room_type_name = room_type_data.get('room_type', '')

            room_type_odoo = hotelRoomType.sudo().search([('name', '=', room_type_name)], limit=1)
            room_odoo = hotelRoom.sudo().search([('name', '=', room_type_code)], limit=1)

            if room_odoo and room_type_odoo:
                line_vals = {
                    'categ_id': room_type_odoo.id,
                    'reserve': [(6, 0, [room_odoo.id])],
                }
                if index == 0 and room_price_summary:
                    line_vals['promotion_price'] = float(room_price_summary)

                reservation_lines.append((0, 0, line_vals))

            else:
                error_msg = f"Could not find room type '{room_type_name}' or room '{room_type_code}' in Odoo"
                raise ValueError(error_msg)

        return reservation_lines

    def create_room_reservation_lines(self, reservation_id, checkin_date, checkout_date):

        try:
            hotelRoomReservationLine = request.env['hotel.room.reservation.line']

            reservation = request.env['hotel.reservation'].sudo().browse(reservation_id)

            if not reservation:
                raise ValueError(f"Reservation with ID {reservation_id} not found")


            created_lines = []
            for line_id in reservation.reservation_line:
                for room in line_id.reserve:

                    overlapping_reservations = hotelRoomReservationLine.sudo().search([
                        ('room_id', '=', room.id),
                        ('status', 'in', ('confirm', 'done')),
                        '|',
                        '&', ('check_in', '<=', checkin_date), ('check_out', '>', checkin_date),
                        '&', ('check_in', '<', checkout_date), ('check_out', '>=', checkout_date),
                    ])

                    if overlapping_reservations:

                        overlap_details = []
                        for overlap in overlapping_reservations:
                            overlap_details.append(f"Room {room.name} from {overlap.check_in} to {overlap.check_out}")

                        raise ValueError(f"Room conflict detected: {'; '.join(overlap_details)}")

                    vals = {
                        'room_id': room.id,
                        'check_in': checkin_date,
                        'check_out': checkout_date,
                        'state': 'assigned',
                        'reservation_id': reservation.id,
                    }

                    room_line = hotelRoomReservationLine.sudo().create(vals)
                    created_lines.append(room_line.id)


                    room.sudo().write({
                        'isroom': False,
                        'status': 'occupied'
                    })

            reservation.sudo().write({'state': 'confirm'})

            return {
                'success': True,
                'created_room_lines': created_lines,
                'message': f'Created {len(created_lines)} room reservation lines'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': 'room_line_creation_error'
            }

    def validate_room_capacity(self, room_stay_info):
        total_capacity = 0
        hotelRoom = request.env['hotel.room']

        for room_type_data in room_stay_info['room_types']:
            room_code = room_type_data.get('room_id', '')
            room = hotelRoom.sudo().search([('name', '=', room_code)], limit=1)

            if room:
                capacity = getattr(room, 'capacity', 2)
                total_capacity += capacity

            else:
                error_msg = f"Room '{room_code}' not found for capacity validation"
                raise ValueError(error_msg)

        total_guests = room_stay_info['adults'] + room_stay_info['children']
        return total_guests <= total_capacity, total_guests, total_capacity

    def validate_room_availability_for_update(self, reservation_id, room_stay_info):

        try:
            hotelRoom = request.env['hotel.room']
            checkin_date = self.datetime_helper.parse_and_format_datetime(
                room_stay_info['checkin_date'], "00:00:00"
            )
            checkout_date = self.datetime_helper.parse_and_format_datetime(
                room_stay_info['checkout_date'], "23:59:59"
            )

            for room_type_data in room_stay_info['room_types']:
                room_code = room_type_data.get('room_id', '')
                room = hotelRoom.sudo().search([('name', '=', room_code)], limit=1)

                if not room:
                    return False, f"Room '{room_code}' not found"


                conflicting_reservations = room.room_reservation_line_ids.filtered(
                    lambda l: l.status in ('confirm', 'done') and
                              l.reservation_id.id != reservation_id and
                              not (checkout_date <= l.check_in or checkin_date >= l.check_out)
                )

                if conflicting_reservations:
                    return False, f"Room '{room_code}' is not available for the selected dates"

            return True, "All rooms available"

        except Exception as e:
            return False, f"Availability check error: {str(e)}"

    def update_hotel_reservation(self, siteminder_id, customer_info, room_stay_info):

        try:
            existing_reservation = self.find_reservation_by_siteminder_id(siteminder_id)
            if not existing_reservation:
                return {
                    'success': False,
                    'error': f'No reservation found with siteminder_id: {siteminder_id}',
                    'error_type': 'not_found_error'
                }


            if existing_reservation.state != 'draft':
                try:

                    existing_reservation.sudo().cancel_reservation()
                    existing_reservation.sudo().set_to_draft_reservation()
                except Exception as e:
                    return {
                        'success': False,
                        'error': f'Could not reset reservation to draft state: {str(e)}',
                        'error_type': 'state_error'
                    }


            hotelRoomReservationLine = request.env['hotel.room.reservation.line']
            remaining_room_lines = hotelRoomReservationLine.sudo().search([
                ('reservation_id', '=', existing_reservation.id)
            ])
            if remaining_room_lines:

                for line in remaining_room_lines:
                    if line.room_id:
                        line.room_id.write({"isroom": True, "status": "available"})
                remaining_room_lines.unlink()


            update_vals = {}
            current_time = datetime.now().strftime("%H:%M:%S")


            if customer_info:
                if customer_info.get('name'):
                    update_vals['customer_name'] = customer_info['name']
                if customer_info.get('email'):
                    update_vals['email'] = customer_info['email']
                if customer_info.get('phone'):
                    update_vals['ph_no'] = customer_info['phone']
                if customer_info and customer_info.get('payment_status'):
                    current_status = existing_reservation.payment
                    new_status = customer_info['payment_status']
                    if not ((current_status == 'paid' and new_status in ['partial_paid', 'not_paid']) or (current_status == 'partial_paid' and new_status == 'not_paid')):
                        update_vals['payment'] = new_status

            if room_stay_info:

                if room_stay_info.get('checkin_date'):
                    checkin_datetime_obj = self.datetime_helper.parse_and_format_datetime(
                        room_stay_info['checkin_date'], current_time
                    )
                    if checkin_datetime_obj:
                        update_vals['checkin'] = fields.Datetime.from_string(checkin_datetime_obj)

                if room_stay_info.get('checkout_date'):
                    checkout_datetime_obj = self.datetime_helper.parse_and_format_datetime(
                        room_stay_info['checkout_date'], current_time
                    )
                    if checkout_datetime_obj:
                        update_vals['checkout'] = fields.Datetime.from_string(checkout_datetime_obj)


                if 'adults' in room_stay_info:
                    update_vals['adults'] = room_stay_info['adults']
                if 'children' in room_stay_info:
                    update_vals['children'] = room_stay_info['children']


                if room_stay_info.get('room_types'):
                    try:

                        if room_stay_info.get('checkin_date') and room_stay_info.get('checkout_date'):
                            is_available, availability_msg = self.validate_room_availability_for_update(
                                existing_reservation.id, room_stay_info
                            )
                            if not is_available:
                                return {
                                    'success': False,
                                    'error': availability_msg,
                                    'error_type': 'availability_error'
                                }


                        existing_reservation.sudo().reservation_line.unlink()


                        new_reservation_lines = self.create_reservation_lines(
                            room_stay_info['room_types'],
                            customer_info.get("amount_after_tax")
                        )
                        update_vals['reservation_line'] = new_reservation_lines


                        is_valid, total_guests, total_capacity = self.validate_room_capacity(room_stay_info)
                        if not is_valid:
                            return {
                                'success': False,
                                'error': f'Insufficient room capacity: {total_guests} guests require {total_capacity} total capacity',
                                'error_type': 'capacity_error'
                            }

                    except ValueError as ve:
                        return {
                            'success': False,
                            'error': str(ve),
                            'error_type': 'validation_error'
                        }


            if update_vals:
                existing_reservation.sudo().write(update_vals)


            existing_reservation.sudo().invalidate_cache()
            updated_reservation = request.env['hotel.reservation'].sudo().browse(existing_reservation.id)

            return {
                'success': True,
                'reservation_id': updated_reservation.id,
                'reservation_no': updated_reservation.reservation_no,
                'customer_name': updated_reservation.customer_name,
                'checkin': room_stay_info.get('checkin_date', ''),
                'checkout': room_stay_info.get('checkout_date', ''),
                'adults': updated_reservation.adults,
                'children': updated_reservation.children,
                'email': updated_reservation.email,
                'phone': updated_reservation.ph_no,
                'state': 'draft',
                'message': 'Reservation updated successfully and set to draft state'
            }

        except Exception as e:
            import traceback
            return {
                'success': False,
                'error': f'Update error: {str(e)}',
                'error_type': 'system_error'
            }

    def create_hotel_reservation(self, customer_info, room_stay_info):


        try:
            current_time = datetime.now().strftime("%H:%M:%S")


            checkin_datetime_obj = self.datetime_helper.parse_and_format_datetime(
                room_stay_info['checkin_date'], current_time
            )
            checkout_datetime_obj = self.datetime_helper.parse_and_format_datetime(
                room_stay_info['checkout_date'], current_time
            )
            is_valid, total_guests, total_capacity = self.validate_room_capacity(room_stay_info)


            if not is_valid:

                return {
                    'success': False,
                    'error': f'Insufficient room capacity: {total_guests} guests require {total_capacity} total capacity',
                    'error_type': 'capacity_error'
                }

            try:
                reservation_lines = self.create_reservation_lines(
                    room_stay_info['room_types'],
                    customer_info.get("amount_after_tax")
                )
            except ValueError as ve:

                return {
                    'success': False,
                    'error': str(ve),
                    'error_type': 'validation_error'
                }

            num_rooms = len(room_stay_info['room_types'])
            total_adults = room_stay_info['adults']
            total_children = room_stay_info['children']

            if num_rooms > 1:
                adults_for_creation = 1
                children_for_creation = 0
            else:
                adults_for_creation = total_adults
                children_for_creation = total_children
            room_price_summary = room_stay_info.get('room_price_summary', '0')
            siteminder_id = room_stay_info.get('siteminder_id', '')

            reservation_vals = {
                'date_order': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'company_id': 1,
                'partner_id': 149,
                'customer_name': customer_info['name'],
                'customer_note': 'Reservation from Siteminder XML',
                'reservation_referent': 'siteminder',
                'pricelist_id': 1,
                'partner_invoice_id': 149,
                'partner_order_id': 149,
                'partner_shipping_id': 149,
                'payment':customer_info['payment_status'],
                'checkin': fields.Datetime.from_string(checkin_datetime_obj) if checkin_datetime_obj else None,
                'checkout': fields.Datetime.from_string(checkout_datetime_obj) if checkout_datetime_obj else None,
                'adults': adults_for_creation,
                'children': children_for_creation,
                'state': 'draft',
                'email': customer_info['email'],
                'ph_no': customer_info['phone'],
                'reservation_line': reservation_lines,
                'room_price_summary': room_price_summary,
                'siteminder_id': siteminder_id
            }
            reservation = request.env['hotel.reservation'].sudo().create(reservation_vals)


            custom_reservation_no = self.reservation_number_generator.generate_next_reservation_number()
            reservation.sudo().write({'reservation_no': custom_reservation_no})


            checkin_datetime = fields.Datetime.from_string(checkin_datetime_obj)
            checkout_datetime = fields.Datetime.from_string(checkout_datetime_obj)

            room_lines_result = self.create_room_reservation_lines(
                reservation.id,
                checkin_datetime,
                checkout_datetime
            )

            if not room_lines_result['success']:

                reservation.sudo().unlink()
                return room_lines_result

            reservation.sudo().write({'state': 'draft'})


            return {
                'success': True,
                'reservation_id': reservation.id,
                'reservation_no': reservation.reservation_no,
                'room_lines_created': room_lines_result['created_room_lines'],
                'message': 'Reservation and room lines created successfully'
            }

        except Exception as e:

            return {
                'success': False,
                'error': str(e),
                'error_type': 'creation_error'
            }




