from datetime import  datetime
import  logging

_logger = logging.getLogger(__name__)

class DateTimeHelper:
    """Helper service for date/time operations"""

    @staticmethod
    def parse_and_format_datetime(date_string, default_time):
        """Parse date string and convert to proper datetime format for Odoo"""
        try:
            if not date_string:
                return None

            date_string = date_string.strip()
            parts = date_string.replace('/', '-').split('-')

            if len(parts) == 3:
                year, month, day = parts
                month = month.zfill(2)
                day = day.zfill(2)
                normalized_date = f"{year}-{month}-{day}"
            else:
                normalized_date = date_string

            parsed_date = datetime.strptime(normalized_date, '%Y-%m-%d')
            datetime_str = f"{normalized_date} {default_time}"
            final_datetime = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')

            return final_datetime

        except ValueError as e:
            _logger.error(f"Error parsing date '{date_string}': {e}")
            return None