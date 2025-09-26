class RoomStayExtractor:


    @staticmethod
    def extract_room_stay_info(hotel_reservation):
        try:
            if not isinstance(hotel_reservation, dict):
                raise ValueError("Invalid hotel_reservation format (not a dict)")

            room_stays_container = hotel_reservation.get('RoomStays', {})
            room_stays = room_stays_container.get('RoomStay', [])

            if not isinstance(room_stays, list):
                room_stays = [room_stays]

            if not room_stays:
                return None

            first_room_stay = room_stays[0]

            # Extract dates
            time_span = first_room_stay.get('TimeSpan', {})
            checkin_date = time_span.get('@Start', '')
            checkout_date = time_span.get('@End', '')

            # Extract guest counts
            guest_counts_container = first_room_stay.get('GuestCounts', {})
            guest_counts = guest_counts_container.get('GuestCount', [])

            if not isinstance(guest_counts, list):
                guest_counts = [guest_counts]

            adults = children = 0


            for guest_count in guest_counts:
                if not isinstance(guest_count, dict):
                    continue

                age_code = guest_count.get('@AgeQualifyingCode', '')
                try:
                    count = int(guest_count.get('@Count', 1))
                except (ValueError, TypeError):
                    count = 1

                if age_code in ['10', '1']:
                    adults += count
                elif age_code in ['8', '7', '2']:
                    children += count
                else:
                    adults += count

            if adults == 0:
                adults = 1

            # Extract room types
            room_types_container = first_room_stay.get('RoomTypes', {})
            room_types_data = room_types_container.get('RoomType', [])

            if not isinstance(room_types_data, list):
                room_types_data = [room_types_data]

            room_types = []
            for rt in room_types_data:
                if not isinstance(rt, dict):
                    continue

                room_type_info = {
                    'room_type_code': rt.get('@RoomTypeCode', ''),
                    'room_type': rt.get('@RoomType', ''),
                    'room_id': rt.get('@RoomID', '')
                }

                room_desc_container = rt.get('RoomDescription', {})
                room_desc_text = room_desc_container.get('Text', '')

                if isinstance(room_desc_text, dict):
                    room_type_info['description'] = room_desc_text.get('#text', '')
                else:
                    room_type_info['description'] = room_desc_text

                room_types.append(room_type_info)

            return {
                'checkin_date': checkin_date,
                'checkout_date': checkout_date,
                'adults': adults,
                'children': children,
                'room_types': room_types
            }

        except Exception as e:
            return None
