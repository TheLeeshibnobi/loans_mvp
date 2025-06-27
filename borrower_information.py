from supabase import create_client, Client
from datetime import date, timedelta, datetime, UTC
from dotenv import load_dotenv
import os


class BorrowerInformation:
    """Contains metrics for the overview dashboard"""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)


    def borrower_standings(self):
        """Returns a dictionary of borrower standing categories mapped to their percentage thresholds."""
        borrower_standings = {
            'perfect standing': 100,  # 100% repayment rate (always pays on time)
            'good standing': 80,  # 80% or higher repayment rate (mostly pays on time)
            'suspect': 50,  # 50% repayment rate (inconsistent payments)
            'bad standing': 49  # Below 50% repayment rate (mostly defaults)
        }
        return borrower_standings

    def risk_standings(self):
        """returns a dictionary that holds the keys of risk assessment of the borrower"""
        risk_card = {
            'cannot_loan': (81, 100, 0),
            'high_risk': (11, 80, 20),
            'moderate_risk': (1, 10, 50),
            'no_risk': (0, 0, 100)
        }

        return risk_card

    def get_borrower_payment_history(self, loan_id):
        """
        determines the borrower status, number of on time payments, number of late payments, last payment
        """

        # Step 1: Get today's date in 'YYYY-MM-DD' format
        today_date = datetime.today().strftime("%Y-%m-%d")

        # Step 2: Query the loans table, filtering for loans where 'due_date' is **before** today
        response = (
            self.supabase
            .table('loans')
            .select('id', 'due_date')
            .eq('id', loan_id)
            .lt('due_date', today_date)  # Filters only loans where due_date is in the past
            .execute()
        )

         # Step 3: Filter loans to include only those where the due date has passed
        due_loans = response.data
        total_due_loans = len(due_loans)

        # Step 4: Check how many due loans were repaid on time
        response = (
            self.supabase
            .table('repayments')
            .select('loan_id', 'repayment_date')
            .eq('loan_id', loan_id)
            .execute()
        )

        repayment_data = response.data
        on_time_repayments = len(repayment_data)

        # Step 5: Avoid division errors and handle edge cases
        if total_due_loans == 0:
            return "Standing Not Determined Yet"

        # Step 6: Calculate repayment percentage based only on due loans
        repayment_percentage = (on_time_repayments / total_due_loans) * 100

        # Step 7: Compare the percentage with predefined standings
        standings = self.borrower_standings()
        for status, threshold in standings.items():
            if repayment_percentage >= threshold:
                payment_history = {
                    'status': status,
                    'on_time_payments': on_time_repayments,
                    'late_payments': max(total_due_loans - on_time_repayments, 0),
                    'last_repayment_date': repayment_data[-1]['repayment_date'] if repayment_data else None
                }

                return payment_history

        return "Unknown Standing"  # Default case if none match


    def total_outstanding_debts(self, borrower_id):
        """returns a dict required for the total outstanding debts information of that borrower"""
        response = (
            self.supabase
            .table('loans')
            .select('amount', 'status', 'due_date')
            .eq('borrower_id', borrower_id)
            .neq('status', 'Completed')
            .execute()
        )

        outstanding_debts = [info['amount'] for info in response.data]
        total_outstanding = sum(float(amount) for amount in outstanding_debts)

        active_loans = [info['status'] for info in response.data if info['status'] != 'Default']
        number_of_active_loans = len(active_loans)

        payment_dates = [info['due_date'] for info in response.data if info.get('due_date')]
        # Convert date strings to datetime.date safely
        dates = []
        for d in payment_dates:
            try:
                dates.append(datetime.strptime(d, '%Y-%m-%d').date())
            except ValueError:
                continue  # skip invalid formats

        # Find the earliest date if list is not empty
        earliest_date = min(dates).strftime('%Y-%m-%d') if dates else None

        outstanding_debts = {
            'total_outstanding': total_outstanding,
            'active_loans': number_of_active_loans,
            'earliest_date': earliest_date
        }

        return outstanding_debts


    def default_risk_assessment(self, borrower_id):
        """Returns information needed for the default risk card on the borrower's information."""
        response = (
            self.supabase
            .table('loans')
            .select('status', 'created_at')
            .eq('borrower_id', borrower_id)
            .execute()
        )

        data = response.data or []  # fallback to empty list if None

        overdue_loans = sum(1 for loan in data if loan['status'] == 'Overdue')
        total_loans = len(data)

        default_percentage = (overdue_loans / total_loans * 100) if total_loans > 0 else 0

        # Risk card with (low, high, score) tuples
        risk_card = self.risk_standings()

        # Default values
        risk_level = 'unknown'
        risk_score = 0

        # Determine the risk level and score
        for level, (low, high, score) in risk_card.items():
            if low <= default_percentage <= high:
                risk_level = level
                risk_score = score
                break

        # Extract and safely convert dates
        borrower_dates = [
            datetime.fromisoformat(info['created_at'])
            for info in data
            if info.get('created_at')
        ]

        earliest_date = min(borrower_dates).date() if borrower_dates else None

        default_assessment = {
            'risk_level': risk_level,
            'risk_score': risk_score,
            'missed_payments': sum(
                1 for info in data if info['status'] in ('Overdue', 'Default')
            ),
            'customer_since': str(earliest_date) if earliest_date else None
        }

        return default_assessment



    def account_status(self, borrower_id):
        """Returns account summary for the borrower's information card."""

        # Fetch loans
        loan_response = (
            self.supabase
            .table('loans')
            .select('id', 'amount', 'created_at')
            .eq('borrower_id', borrower_id)
            .execute()
        )

        loan_data = loan_response.data or []

        if not loan_data:
            return {
                "total_loaned": 0,
                "total_repaid": 0,
                "credit_limit": 0,
                "last_contract": None
            }

        # Get the latest loan date
        loan_dates = [
            datetime.fromisoformat(info['created_at'])
            for info in loan_data
            if info.get('created_at')
        ]
        latest_date = max(loan_dates).date() if loan_dates else None

        # Calculate total loaned
        total_loaned = sum(
            float(info['amount']) for info in loan_data
            if info.get('amount') not in [None, '']
        )

        # Get repayments in one go
        loan_ids = [info['id'] for info in loan_data]
        repayment_response = (
            self.supabase
            .table('repayments')
            .select('amount', 'loan_id')
            .in_('loan_id', loan_ids)
            .execute()
        )

        repayment_data = repayment_response.data or []
        repaid_amounts = [
            float(info['amount']) for info in repayment_data
            if info.get('amount') not in [None, '']
        ]
        total_repaid = sum(repaid_amounts)

        credit_status = {
            "total_loaned": total_loaned,
            "total_repaid": total_repaid,
            "credit_limit": total_repaid * 2.5,
            "total_income_interest" : total_repaid - total_loaned,
            "last_contract": str(latest_date) if latest_date else None
        }

        return credit_status


    def recent_borrower_history(self, borrower_id):
        """Returns a list of dictionaries representing the borrower's 3 most recent loans."""
        recent_history = []

        response = (
            self.supabase
            .table('loans')
            .select('*')
            .eq('borrower_id', borrower_id)
            .order('created_at', desc=True)
            .limit(3)
            .execute()
        )

        raw_data = response.data

        for data in raw_data:
            # Fetch and sum repayment amounts
            repayment_response = (
                self.supabase
                .table('repayments')
                .select('amount')
                .eq('loan_id', data['id'])
                .execute()
            )

            repaid_amount = sum([item['amount'] for item in repayment_response.data]) if repayment_response.data else 0

            created_at_date = datetime.fromisoformat(data['created_at']).date()

            loan_info = {
                'start_date': str(created_at_date),
                'amount': data['amount'],
                'interest_rate': f"{data['interest_rate']}%",
                'end_date': data['due_date'][:10],  # Clean date
                'status': data['status'],
                'repaid_amount': repaid_amount,
                'balance': round(
                    float(data['amount'] + data['amount'] * data['interest_rate'] / 100) - float(repaid_amount), 2)
            }

            recent_history.append(loan_info)

        return recent_history



