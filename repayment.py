from supabase import create_client, Client
import datetime
import os
from registration import Registration




class Repayment:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

        self.reg_tool = Registration()

    def show_loans(self, nrc):
        """returns a list of active, default and overdue loans for that borrower using the nrc as parameter"""
        # get the borrower_id
        borrower_data = self.reg_tool.get_borrower_id(nrc)
        borrower_id =  borrower_data.get('id')
        loans = self.get_loans(borrower_id)
        return loans

    def get_loans(self, borrower_id):
        """Returns a list of active, default, and overdue loans using borrower_id."""
        loans_response = (
            self.supabase
            .table('loans')
            .select('*')
            .eq('borrower_id', borrower_id)
            .in_('status', ['Overdue', 'Default', 'Active'])
            .execute()
        )

        return loans_response.data

    def submit_repayment(self, loan_id, status, amount, repayment_date, discount):
        """Submits the repayment of a loan and updates the loan status."""

        # Ensure amount is a float
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            print("Invalid amount")
            return

        # 1. Record repayment in the 'repayments' table
        repayment_data = {
            'loan_id': loan_id,
            'amount': amount,
            'repayment_date': repayment_date,  # ISO 8601 format: YYYY-MM-DD
            'discount' : discount
        }

        insert_response = self.supabase.table('repayments').insert(repayment_data).execute()

        if not insert_response.data:
            print("Repayment insertion failed.")
            return

        print("Repayment recorded successfully.")

        # 2. Get current loan amount
        loan_response = (
            self.supabase
            .table('loans')
            .select('amount')
            .eq('id', loan_id)
            .execute()
        )

        if not loan_response.data:
            print("Loan not found.")
            return

        current_amount = loan_response.data[0]['amount']
        updated_amount = current_amount - amount - float(discount)

        # Prevent negative loan amount
        if updated_amount < 0:
            updated_amount = 0

        # 3. Update loan with new amount and status
        update_response = (
            self.supabase
            .table("loans")
            .update({
                "amount": updated_amount,
                "status": status
            })
            .eq("id", loan_id)
            .execute()
        )

        if update_response.data:
            print("Loan status and amount updated successfully.")
        else:
            print("Loan update failed.")

    def get_loan_by_id(self, loan_id):
        """returns the full row of the loan specific to that loan id"""
        print(f"Fetching loan with ID: {loan_id}")  # Debug
        response = (
            self.supabase
            .table('loans')
            .select('*')
            .eq('id', loan_id)  # No conversion needed - use UUID string directly
            .execute()
        )
        print(f"Loan data found: {response.data}")  # Debug
        return response.data


