from supabase import create_client, Client
from datetime import date, timedelta, datetime, UTC
from dotenv import load_dotenv
import os


class Registration:
    """Contains metrics for the overview dashboard"""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

    def check_borrower(self, nrc):
        """Checks if a borrower is registered in the database using the NRC number"""
        response = (
            self.supabase
            .table('borrowers')
            .select('nrc_number')
            .eq('nrc_number', nrc)
            .execute()
        )

        return bool(response.data)  # This is simpler


    def get_borrower_id(self, nrc):
        """Returns borrower information using the borrower nrc"""
        if self.check_borrower(nrc):
            response = (
                self.supabase
                .table('borrowers')
                .select('*')
                .eq('nrc_number', nrc)
                .limit(1)  # Good practice
                .execute()
            )
            return response.data[0]
        else:
            return None  # Return None instead of string

    def get_borrower_data(self, borrower_id):
        """returns th borrower information using the borrower id"""
        response = (
            self.supabase
            .table('borrowers')
            .select('*')
            .eq('id', borrower_id)
            .limit(1)  # Good practice
            .execute()
        )
        return response.data[0]





    def update_loan_table(self, amount, status, interest_rate, duration_days, due_date, nrc):
        """Records a new loan in the loan table and returns the loan ID"""
        raw_borrower_data = self.get_borrower_id(nrc)
        if not raw_borrower_data:
            return "Borrower not found"

        data = {
            'borrower_id': raw_borrower_data['id'],
            'amount': amount,
            'status': status,
            'interest_rate': interest_rate,
            'duration_days': duration_days,
            'due_date': due_date
        }

        response = self.supabase.table('loans').insert(data).execute()

        if response.data and isinstance(response.data, list):
            loan_id = response.data[0].get('id')
            return loan_id
        else:
            return "Insert failed or loan ID not returned"

    def insert_to_loans_and_disbursements_tables(self, amount, status, interest_rate, duration_days, due_date, nrc):
        """
        Inserts a new loan into the loans table and records the disbursement.

        Parameters:
        - amount: float
        - status: str
        - interest_rate: float
        - duration_days: int
        - due_date: str or datetime
        - nrc: str

        Returns:
        - str indicating success or failure.
        """
        loan_id = self.update_loan_table(amount, status, interest_rate, duration_days, due_date, nrc)

        if not loan_id:
            return 'Loan insertion failed'

        data = {
            'loan_id': loan_id,
            'amount': amount,
        }

        try:
            response = self.supabase.table('disbursements').insert(data).execute()

            if response.data:
                return 'Posted successfully'
            else:
                return f"Post unsuccessful: {response.error.message if response.error else 'Unknown error'}"
        except Exception as e:
            return f"Error posting to disbursements: {str(e)}"

    def register_borrower(self,name, gender, location, nrc, mobile, occupation, birth_date):
        """registers the borrower to the database"""

        data = {
            'name' : name,
            'gender' : gender,
            'location' : location,
            'nrc_number' : nrc,
            'mobile' : mobile,
            'occupation' : occupation,
            'birth_date' : birth_date
        }
        response = self.supabase.table("orders").insert(data).execute()
        if response.status_code != 201:
            print("Error inserting data:", response.data)
        else:
            print("Insert successful:", response.data)

    def get_loan_id(self, borrower_id):
        """returns the loan id of that specific borrower"""
        response = (
            self.supabase
            .table('loans')
            .select('id')
            .eq('borrower_id', borrower_id)
            .execute()
        )

        return response.data[0]['id']

    def register_new_borrower(self, name, gender, location, nrc_number, mobile, occupation, birth_date, notes):
        """Registers a new borrower who is not already in the database."""
        data = {
            'name': name,
            'gender': gender,
            'location': location,
            'nrc_number': nrc_number,
            'mobile': mobile,
            'occupation': occupation,
            'birth_date': birth_date,
            'notes': [notes]
        }

        try:
            response = self.supabase.table('borrowers').insert(data).execute()
            print(f" Borrower '{name}' successfully registered.")
            return response
        except Exception as e:
            print(f" Error registering borrower: {e}")
            return None


# testing
