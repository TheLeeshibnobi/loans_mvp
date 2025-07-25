from supabase import create_client, Client
from datetime import date, timedelta, datetime, UTC
from dotenv import load_dotenv
import os


class Registration:
    """Contains metrics for registration of borrowers and loans"""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        try:
            self.supabase: Client = create_client(url, service_role_key)
        except Exception as e:
            raise ValueError(f"Failed to create Supabase client: {str(e)}")

    def check_borrower(self, nrc, business_id):
        """Checks if a borrower is registered in the database using the NRC number for a specific business"""
        try:
            if not nrc or not str(nrc).strip():
                return False

            response = (
                self.supabase
                .table('borrowers')
                .select('nrc_number')
                .eq('nrc_number', str(nrc).strip())
                .eq('business_id', business_id)
                .execute()
            )

            return bool(response and response.data)
        except Exception as e:
            print(f"Error checking borrower with NRC {nrc}: {str(e)}")
            return False

    def get_borrower_id(self, nrc, business_id):
        """Returns borrower information using the borrower nrc for a specific business"""
        try:
            if not nrc or not str(nrc).strip():
                return None

            if self.check_borrower(nrc, business_id):
                response = (
                    self.supabase
                    .table('borrowers')
                    .select('*')
                    .eq('nrc_number', str(nrc).strip())
                    .eq('business_id', business_id)
                    .limit(1)
                    .execute()
                )

                if response and response.data and len(response.data) > 0:
                    return response.data[0]
                else:
                    return None
            else:
                return None
        except Exception as e:
            print(f"Error getting borrower with NRC {nrc}: {str(e)}")
            return None

    def get_borrower_data(self, borrower_id, business_id):
        """returns the borrower information using the borrower id for a specific business"""
        try:
            if not borrower_id:
                return None

            response = (
                self.supabase
                .table('borrowers')
                .select('*')
                .eq('id', borrower_id)
                .eq('business_id', business_id)
                .limit(1)
                .execute()
            )

            if response and response.data and len(response.data) > 0:
                return response.data[0]
            else:
                return None
        except Exception as e:
            print(f"Error getting borrower data for ID {borrower_id}: {str(e)}")
            return None

    def update_loan_table(self, amount, status, interest_rate, duration_days, due_date, nrc, business_id):
        """Records a new loan in the loan table and returns the loan ID for a specific business"""
        try:
            # Validate inputs
            if not nrc or not str(nrc).strip():
                return "Invalid NRC provided"

            if not amount or float(amount) <= 0:
                return "Invalid loan amount"

            raw_borrower_data = self.get_borrower_id(nrc, business_id)
            if not raw_borrower_data:
                return "Borrower not found"

            data = {
                'borrower_id': raw_borrower_data['id'],
                'amount': float(amount),
                'status': str(status) if status else 'Pending',
                'interest_rate': float(interest_rate) if interest_rate else 0.0,
                'duration_days': int(duration_days) if duration_days else 0,
                'due_date': due_date,
                'business_id': business_id
            }

            response = self.supabase.table('loans').insert(data).execute()

            if response and response.data and isinstance(response.data, list) and len(response.data) > 0:
                loan_id = response.data[0].get('id')
                if loan_id:
                    return loan_id
                else:
                    return "Loan ID not returned from database"
            else:
                error_msg = "Insert failed"
                if hasattr(response, 'error') and response.error:
                    error_msg += f": {response.error.message}"
                return error_msg
        except (ValueError, TypeError) as e:
            return f"Invalid data provided: {str(e)}"
        except Exception as e:
            print(f"Error updating loan table: {str(e)}")
            return f"Database error: {str(e)}"

    def insert_to_loans_and_disbursements_tables(self, amount, status, interest_rate, duration_days, due_date, nrc, business_id):
        """
        Inserts a new loan into the loans table and records the disbursement for a specific business.

        Parameters:
        - amount: float
        - status: str
        - interest_rate: float
        - duration_days: int
        - due_date: str or datetime
        - nrc: str
        - business_id: business identifier

        Returns:
        - str indicating success or failure.
        """
        try:
            # Validate inputs
            if not amount or float(amount) <= 0:
                return "Invalid loan amount provided"

            loan_id = self.update_loan_table(amount, status, interest_rate, duration_days, due_date, nrc, business_id)

            # Check if loan_id is actually an ID or an error message
            if not loan_id or isinstance(loan_id, str) and not loan_id.isdigit():
                if isinstance(loan_id, str) and "not found" in loan_id.lower():
                    return loan_id
                return 'Loan insertion failed'

            data = {
                'loan_id': loan_id,
                'amount': float(amount),
                'business_id': business_id
            }

            response = self.supabase.table('disbursements').insert(data).execute()

            if response and response.data:
                return 'Posted successfully'
            else:
                error_msg = "Post unsuccessful"
                if hasattr(response, 'error') and response.error:
                    error_msg += f": {response.error.message}"
                else:
                    error_msg += ": Unknown error"
                return error_msg
        except (ValueError, TypeError) as e:
            return f"Invalid data provided: {str(e)}"
        except Exception as e:
            print(f"Error posting to disbursements: {str(e)}")
            return f"Error posting to disbursements: {str(e)}"

    def register_borrower(self, name, gender, location, nrc, mobile, occupation, birth_date, business_id):
        """registers the borrower to the database for a specific business"""
        try:
            # Validate required fields
            if not name or not str(name).strip():
                print("Error: Name is required")
                return False

            if not nrc or not str(nrc).strip():
                print("Error: NRC number is required")
                return False

            data = {
                'name': str(name).strip(),
                'gender': str(gender).strip() if gender else None,
                'location': str(location).strip() if location else None,
                'nrc_number': str(nrc).strip(),
                'mobile': str(mobile).strip() if mobile else None,
                'occupation': str(occupation).strip() if occupation else None,
                'birth_date': birth_date,
                'business_id': business_id
            }

            # Note: The original code inserts to "orders" table, keeping this as is
            # but adding error handling
            response = self.supabase.table("orders").insert(data).execute()

            if hasattr(response, 'status_code'):
                if response.status_code != 201:
                    print("Error inserting data:", response.data if hasattr(response, 'data') else 'Unknown error')
                    return False
                else:
                    print("Insert successful:", response.data if hasattr(response, 'data') else 'Success')
                    return True
            else:
                # For newer supabase versions that don't have status_code
                if response and response.data:
                    print("Insert successful:", response.data)
                    return True
                else:
                    error_msg = "Insert failed"
                    if hasattr(response, 'error') and response.error:
                        error_msg += f": {response.error.message}"
                    print("Error inserting data:", error_msg)
                    return False
        except Exception as e:
            print(f"Error registering borrower: {str(e)}")
            return False

    def get_loan_id(self, borrower_id, business_id):
        """returns the loan id of that specific borrower for a specific business"""
        try:
            if not borrower_id:
                return None

            response = (
                self.supabase
                .table('loans')
                .select('id')
                .eq('borrower_id', borrower_id)
                .eq('business_id', business_id)
                .execute()
            )

            if response and response.data and len(response.data) > 0:
                return response.data[0].get('id')
            else:
                return None
        except Exception as e:
            print(f"Error getting loan ID for borrower {borrower_id}: {str(e)}")
            return None

    def register_new_borrower(self, name, gender, location, nrc_number, mobile, occupation, birth_date, notes, business_id):
        """Registers a new borrower who is not already in the database for a specific business."""
        try:
            # Validate required fields
            if not name or not str(name).strip():
                print("Error: Name is required")
                return None

            if not nrc_number or not str(nrc_number).strip():
                print("Error: NRC number is required")
                return None

            # Check if borrower already exists
            if self.check_borrower(nrc_number, business_id):
                print(f"Error: Borrower with NRC {nrc_number} already exists")
                return None

            data = {
                'name': str(name).strip(),
                'gender': str(gender).strip() if gender else None,
                'location': str(location).strip() if location else None,
                'nrc_number': str(nrc_number).strip(),
                'mobile': str(mobile).strip() if mobile else None,
                'occupation': str(occupation).strip() if occupation else None,
                'birth_date': birth_date,
                'notes': [str(notes)] if notes else [],
                'business_id': business_id
            }

            response = self.supabase.table('borrowers').insert(data).execute()

            if response and response.data:
                print(f"Borrower '{name}' successfully registered.")
                return response
            else:
                error_msg = "Registration failed"
                if hasattr(response, 'error') and response.error:
                    error_msg += f": {response.error.message}"
                print(f"Error registering borrower: {error_msg}")
                return None
        except Exception as e:
            print(f"Error registering borrower: {str(e)}")
            return None

    def get_all_loans_for_borrower(self, borrower_id, business_id):
        """Returns all loans for a specific borrower in a specific business - utility method"""
        try:
            if not borrower_id:
                return []

            response = (
                self.supabase
                .table('loans')
                .select('*')
                .eq('borrower_id', borrower_id)
                .eq('business_id', business_id)
                .execute()
            )

            if response and response.data:
                return response.data
            else:
                return []
        except Exception as e:
            print(f"Error getting loans for borrower {borrower_id}: {str(e)}")
            return []

    def validate_borrower_data(self, name, nrc_number, mobile=None):
        """Validates borrower data before registration - utility method"""
        errors = []

        if not name or not str(name).strip():
            errors.append("Name is required")

        if not nrc_number or not str(nrc_number).strip():
            errors.append("NRC number is required")
        elif len(str(nrc_number).strip()) < 6:  # Basic NRC validation
            errors.append("NRC number appears to be too short")

        if mobile and len(str(mobile).strip()) > 0:
            # Basic mobile validation - adjust regex as needed for your country
            import re
            mobile_pattern = r'^[\+]?[0-9\s\-\(\)]{7,15}$'
            if not re.match(mobile_pattern, str(mobile).strip()):
                errors.append("Mobile number format is invalid")

        return errors

# testing