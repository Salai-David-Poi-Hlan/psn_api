import re

class CustomerDataExtractor:
    """Service for extracting customer information from reservation data"""

    @staticmethod
    def extract_customer_info(hotel_reservation):
        """Extract customer information from hotel reservation"""
        res_global_info = hotel_reservation.get('ResGlobalInfo', {})
        profiles_container = res_global_info.get('Profiles', {})
        profile_info = profiles_container.get('ProfileInfo', {})
        profile = profile_info.get('Profile', {})
        customer = profile.get('Customer', {})

        person_name = customer.get('PersonName', {})
        first_name = person_name.get('GivenName', '')
        last_name = person_name.get('Surname', '')
        customer_name = f"{first_name} {last_name}".strip()

        # Extract contact info
        telephone = customer.get('Telephone', {})
        phone_raw = telephone.get('@PhoneNumber', '') if isinstance(telephone, dict) else ''
        phone = re.sub(r'\D', '', phone_raw)  # Keep only digits

        email = customer.get('Email', '')
        if isinstance(email, dict):
            email = email.get('#text', '')

        return {
            'name': customer_name,
            'email': email,
            'phone': phone
        }
