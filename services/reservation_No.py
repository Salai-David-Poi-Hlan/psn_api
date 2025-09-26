from odoo.http import request

class ReservationNumberGenerator:

    @staticmethod
    def generate_next_reservation_number():
        hotelReservation = request.env['hotel.reservation']

        all_reservations = hotelReservation.sudo().search([
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
        return f"R/{next_number:05d}"