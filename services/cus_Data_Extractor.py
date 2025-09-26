import re

class CustomerDataExtractor:

    @staticmethod
    def extract_customer_info(hotel_reservation):
        res_global_info = hotel_reservation.get('ResGlobalInfo', {})
        profiles_container = res_global_info.get("Profiles", {})
        profile_infos = profiles_container.get("ProfileInfo", [])


        if isinstance(profile_infos, dict):
            profile_infos = [profile_infos]

        first_profile_info = next(
            (p for p in profile_infos if p.get('Profile', {}).get('@ProfileType') == '1'),
            profile_infos[0] if profile_infos else {}
        )
        profile = first_profile_info.get("Profile", {})
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


        payment_status = "not_paid"

        deposit_payments = res_global_info.get("DepositPayments", {})
        guarantee_payments = deposit_payments.get("GuaranteePayment", [])

        if isinstance(guarantee_payments, dict):
            guarantee_payments = [guarantee_payments]

        if guarantee_payments:
            first_guarantee = guarantee_payments[0]
            amount_percent = first_guarantee.get("AmountPercent", {})
            percent_str = amount_percent.get("@Percent")
            try:
                percent = float(percent_str)
                if percent == 100:
                    payment_status = "paid"
                elif percent > 0:
                    payment_status = "partial_paid"
            except (TypeError, ValueError):
                pass

        return {
            'name': customer_name,
            'email': email,
            'phone': phone,
            'amount_after_tax': amount_after_tax,
            'siteminder_id': siteminder_id,
            'payment_status': payment_status
        }
