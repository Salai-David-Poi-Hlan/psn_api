import re


class CustomerDataExtractor:

    @staticmethod
    def extract_customer_info(hotel_reservation):
        res_global_info = hotel_reservation.get('ResGlobalInfo', {})
        profiles_container = res_global_info.get("Profiles", {})
        profile_info = profiles_container.get("ProfileInfo", {})
        profile = profile_info.get("Profile", {})
        customer = profile.get("Customer", {})

        person_name = customer.get('PersonName', {})
        first_name = person_name.get("GivenName", '')
        last_name = person_name.get("Surname", '')
        customer_name = f'{first_name} {last_name}'.strip()

        telephone = customer.get('Telephone', {})
        phone_raw = telephone.get("@PhoneNumber", '') if isinstance(telephone, dict) else ''
        phone = re.sub(r'\D', '', phone_raw)

        email = customer.get('Email', '')
        if isinstance(email, dict):
            email = email.get("#text", '')



        total_element = res_global_info.get('Total', {})
        amount_after_tax = total_element.get('@AmountAfterTax', '0')

        hotel_reservation_ids = res_global_info.get('HotelReservationIDs', {})
        hotel_reservation_id = hotel_reservation_ids.get('HotelReservationID', {})
        siteminder_id = hotel_reservation_id.get('@ResID_Value', '')

        return {
            'name': customer_name,
            'email': email,
            'phone': phone,
            'amount_after_tax': amount_after_tax,
            'siteminder_id': siteminder_id
        }