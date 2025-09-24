from odoo.http import request
from .dataTime_Service import  DateTimeHelper
from .reservation_No import  ReservationNumberGenerator
from datetime import  datetime
from odoo import  fields





class ReservationService:


    def __init__(self):
        self.datetime_helper = DateTimeHelper()
        self.reservation_number_generator = ReservationNumberGenerator()

    def create_reservation_lines(self, room_types, room_price_summary=None):

        HotelRoomType = request.env['hotel.room.type']
        HotelRoom = request.env['hotel.room']

        reservation_lines = []

        for index, room_type_data in enumerate(room_types):
            room_type_code = room_type_data.get('room_id', '')
            room_type_name = room_type_data.get('room_type', '')



            room_type_odoo = HotelRoomType.sudo().search([('name', '=', room_type_name)], limit=1)
            room_odoo = HotelRoom.sudo().search([('name', '=', room_type_code)], limit=1)

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

    def validate_room_capacity(self, room_stay_info):
        total_capacity = 0
        HotelRoom = request.env['hotel.room']

        for room_type_data in room_stay_info['room_types']:
            room_code = room_type_data.get('room_id', '')
            room = HotelRoom.sudo().search([('name', '=', room_code)], limit=1)

            if room:
                capacity = getattr(room, 'capacity', 2)
                total_capacity += capacity

            else:
                error_msg = f"Room '{room_code}' not found for capacity validation"
                raise ValueError(error_msg)

        total_guests = room_stay_info['adults'] + room_stay_info['children']
        return total_guests <= total_capacity, total_guests, total_capacity




    def create_hotel_reservation(self, customer_info, room_stay_info):

        try:
            HotelReservation = request.env['hotel.reservation']
            new_reservation_no = self.reservation_number_generator.generate_next_reservation_number()
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
                reservation_lines = self.create_reservation_lines(room_stay_info['room_types'], customer_info.get("amount_after_tax"))
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
                use_workaround = True
            else:

                adults_for_creation = total_adults
                children_for_creation = total_children
                use_workaround = False

            room_price_summary = room_stay_info.get('room_price_summary', '0')
            siteminder_id=room_stay_info.get('siteminder_id','')
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
                'checkin': fields.Datetime.from_string(checkin_datetime_obj) if checkin_datetime_obj else None,
                'checkout': fields.Datetime.from_string(checkout_datetime_obj) if checkout_datetime_obj else None,
                'adults': adults_for_creation,
                'children': children_for_creation,
                'passport':'123456789',
                'state': 'draft',
                'payment': 'paid',
                'payment_method':17,
                'email': customer_info['email'],
                'ph_no': customer_info['phone'],
                'reservation_line': reservation_lines,
                'room_price_summary':room_price_summary,
                'reservation_referent': 'siteminder',
                'siteminder_id':siteminder_id
            }
            new_reservation = HotelReservation.sudo().create(reservation_vals)


            if use_workaround:
                new_reservation.sudo().with_context(duplicate=True).write({
                        'reservation_no': new_reservation_no,
                        'adults': total_adults,
                        'children': total_children,
                })

            else:
                new_reservation.sudo().write({'reservation_no': new_reservation_no})

            new_reservation.sudo().invalidate_cache()
            updated_reservation = HotelReservation.sudo().browse(new_reservation.id)


            try:
                updated_reservation.sudo().confirmed_reservation()

                updated_reservation.sudo().invalidate_cache()
                final_reservation = HotelReservation.sudo().browse(new_reservation.id)
                if final_reservation.state != 'confirm':
                    raise Exception(f"Reservation state is '{final_reservation.state}', expected 'confirm'")
            except Exception as e:


                try:
                    updated_reservation.sudo().cancel_reservation()
                    updated_reservation.sudo().set_to_draft_reservation()
                    updated_reservation.sudo().unlink()

                except Exception as cleanup_error:

                    return {
                    'success': False,
                     'error': f'Reservation cleanup failed: {str(cleanup_error)}',
                     'error_type': 'cleanup_error'
                    }
                return {
                    'success': False,
                    'error': f'Reservation could not be confirmed: {str(e)}',
                    'error_type': 'confirmation_error'
                }
            return {
                'success': True,
                'reservation_id': updated_reservation.id,
                'reservation_no': updated_reservation.reservation_no,
                'customer_name': customer_info['name'],
                'checkin': room_stay_info['checkin_date'],
                'checkout': room_stay_info['checkout_date'],
                'adults': total_adults,
                'children': total_children,
                'email': customer_info['email'],
                'phone': customer_info['phone'],
                'state': 'confirm',
                'message': 'Reservation created and confirmed successfully'
            }

        except Exception as e:
            import traceback
            return {
                'success': False,
                'error': f'Error: {str(e)}',
                'error_type': 'system_error'
            }