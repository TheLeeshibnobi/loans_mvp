from supabase import create_client, Client
from datetime import date, timedelta, datetime, UTC
from dotenv import load_dotenv
import os
import logging

# Set up logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


class BorrowerInformation:
    """Contains metrics for the overview dashboard"""

    def __init__(self):
        try:
            url = os.getenv("SUPABASE_URL")
            service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

            if not url or not service_role_key:
                raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

            self.supabase: Client = create_client(url, service_role_key)
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise

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
        try:
            if not loan_id:
                return {
                    'status': 'Standing Not Determined Yet',
                    'on_time_payments': 0,
                    'late_payments': 0,
                    'last_repayment_date': None
                }

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

            # Check for database errors
            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error in get_borrower_payment_history: {response.error}")
                return "Standing Not Determined Yet"

            # Step 3: Filter loans to include only those where the due date has passed
            due_loans = response.data or []
            total_due_loans = len(due_loans)

            # Step 4: Check how many due loans were repaid on time
            repayment_response = (
                self.supabase
                .table('repayments')
                .select('loan_id', 'repayment_date')
                .eq('loan_id', loan_id)
                .execute()
            )

            if hasattr(repayment_response, 'error') and repayment_response.error:
                logger.error(f"Database error in repayments query: {repayment_response.error}")
                return "Standing Not Determined Yet"

            repayment_data = repayment_response.data or []
            on_time_repayments = len(repayment_data)

            # Step 5: Avoid division errors and handle edge cases
            if total_due_loans == 0:
                return {
                    'status': 'Standing Not Determined Yet',
                    'on_time_payments': on_time_repayments,
                    'late_payments': 0,
                    'last_repayment_date': repayment_data[-1]['repayment_date'] if repayment_data else None
                }

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

            # Default case - bad standing
            return {
                'status': 'bad standing',
                'on_time_payments': on_time_repayments,
                'late_payments': max(total_due_loans - on_time_repayments, 0),
                'last_repayment_date': repayment_data[-1]['repayment_date'] if repayment_data else None
            }

        except Exception as e:
            logger.error(f"Error in get_borrower_payment_history: {e}")
            return {
                'status': 'Standing Not Determined Yet',
                'on_time_payments': 0,
                'late_payments': 0,
                'last_repayment_date': None
            }

    def total_outstanding_debts(self, borrower_id):
        """returns a dict required for the total outstanding debts information of that borrower"""
        try:
            if not borrower_id:
                return {
                    'total_outstanding': 0,
                    'active_loans': 0,
                    'earliest_date': None
                }

            response = (
                self.supabase
                .table('loans')
                .select('amount', 'status', 'due_date')
                .eq('borrower_id', borrower_id)
                .neq('status', 'Completed')
                .execute()
            )

            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error in total_outstanding_debts: {response.error}")
                return {
                    'total_outstanding': 0,
                    'active_loans': 0,
                    'earliest_date': None
                }

            loan_data = response.data or []

            if not loan_data:
                return {
                    'total_outstanding': 0,
                    'active_loans': 0,
                    'earliest_date': None
                }

            # Calculate total outstanding with error handling
            outstanding_debts = []
            for info in loan_data:
                try:
                    amount = float(info.get('amount', 0))
                    outstanding_debts.append(amount)
                except (ValueError, TypeError):
                    continue

            total_outstanding = sum(outstanding_debts)

            # Count active loans
            active_loans = [
                info['status'] for info in loan_data
                if info.get('status') and info['status'] != 'Default'
            ]
            number_of_active_loans = len(active_loans)

            # Handle payment dates
            payment_dates = [
                info['due_date'] for info in loan_data
                if info.get('due_date')
            ]

            dates = []
            for d in payment_dates:
                try:
                    dates.append(datetime.strptime(d, '%Y-%m-%d').date())
                except (ValueError, TypeError):
                    continue

            earliest_date = min(dates).strftime('%Y-%m-%d') if dates else None

            outstanding_debts = {
                'total_outstanding': total_outstanding,
                'active_loans': number_of_active_loans,
                'earliest_date': earliest_date
            }

            return outstanding_debts

        except Exception as e:
            logger.error(f"Error in total_outstanding_debts: {e}")
            return {
                'total_outstanding': 0,
                'active_loans': 0,
                'earliest_date': None
            }

    def default_risk_assessment(self, borrower_id):
        """Returns information needed for the default risk card on the borrower's information."""
        try:
            if not borrower_id:
                return {
                    'risk_level': 'no_risk',
                    'risk_score': 100,
                    'missed_payments': 0,
                    'customer_since': None
                }

            response = (
                self.supabase
                .table('loans')
                .select('status', 'created_at')
                .eq('borrower_id', borrower_id)
                .execute()
            )

            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error in default_risk_assessment: {response.error}")
                return {
                    'risk_level': 'unknown',
                    'risk_score': 0,
                    'missed_payments': 0,
                    'customer_since': None
                }

            data = response.data or []

            if not data:
                return {
                    'risk_level': 'no_risk',
                    'risk_score': 100,
                    'missed_payments': 0,
                    'customer_since': None
                }

            overdue_loans = sum(1 for loan in data if loan.get('status') == 'Overdue')
            total_loans = len(data)

            default_percentage = (overdue_loans / total_loans * 100) if total_loans > 0 else 0

            # Risk card with (low, high, score) tuples
            risk_card = self.risk_standings()

            # Default values
            risk_level = 'no_risk'
            risk_score = 100

            # Determine the risk level and score
            for level, (low, high, score) in risk_card.items():
                if low <= default_percentage <= high:
                    risk_level = level
                    risk_score = score
                    break

            # Extract and safely convert dates
            borrower_dates = []
            for info in data:
                if info.get('created_at'):
                    try:
                        borrower_dates.append(datetime.fromisoformat(info['created_at']))
                    except (ValueError, TypeError):
                        continue

            earliest_date = min(borrower_dates).date() if borrower_dates else None

            default_assessment = {
                'risk_level': risk_level,
                'risk_score': risk_score,
                'missed_payments': sum(
                    1 for info in data
                    if info.get('status') in ('Overdue', 'Default')
                ),
                'customer_since': str(earliest_date) if earliest_date else None
            }

            return default_assessment

        except Exception as e:
            logger.error(f"Error in default_risk_assessment: {e}")
            return {
                'risk_level': 'unknown',
                'risk_score': 0,
                'missed_payments': 0,
                'customer_since': None
            }

    def account_status(self, borrower_id):
        """Returns account summary for the borrower's information card."""
        try:
            if not borrower_id:
                return {
                    "total_loaned": 0,
                    "total_repaid": 0,
                    "credit_limit": 0,
                    "total_income_interest": 0,
                    "last_contract": None
                }

            # Fetch loans
            loan_response = (
                self.supabase
                .table('loans')
                .select('id', 'amount', 'created_at')
                .eq('borrower_id', borrower_id)
                .execute()
            )

            if hasattr(loan_response, 'error') and loan_response.error:
                logger.error(f"Database error in account_status: {loan_response.error}")
                return {
                    "total_loaned": 0,
                    "total_repaid": 0,
                    "credit_limit": 0,
                    "total_income_interest": 0,
                    "last_contract": None
                }

            loan_data = loan_response.data or []

            if not loan_data:
                return {
                    "total_loaned": 0,
                    "total_repaid": 0,
                    "credit_limit": 0,
                    "total_income_interest": 0,
                    "last_contract": None
                }

            # Get the latest loan date
            loan_dates = []
            for info in loan_data:
                if info.get('created_at'):
                    try:
                        loan_dates.append(datetime.fromisoformat(info['created_at']))
                    except (ValueError, TypeError):
                        continue

            latest_date = max(loan_dates).date() if loan_dates else None

            # Calculate total loaned
            total_loaned = 0
            for info in loan_data:
                try:
                    amount = info.get('amount')
                    if amount is not None and amount != '':
                        total_loaned += float(amount)
                except (ValueError, TypeError):
                    continue

            # Get repayments in one go
            loan_ids = [info['id'] for info in loan_data if info.get('id')]

            if not loan_ids:
                return {
                    "total_loaned": total_loaned,
                    "total_repaid": 0,
                    "credit_limit": 0,
                    "total_income_interest": -total_loaned,
                    "last_contract": str(latest_date) if latest_date else None
                }

            repayment_response = (
                self.supabase
                .table('repayments')
                .select('amount', 'loan_id')
                .in_('loan_id', loan_ids)
                .execute()
            )

            if hasattr(repayment_response, 'error') and repayment_response.error:
                logger.error(f"Database error in repayments query: {repayment_response.error}")
                total_repaid = 0
            else:
                repayment_data = repayment_response.data or []
                total_repaid = 0
                for info in repayment_data:
                    try:
                        amount = info.get('amount')
                        if amount is not None and amount != '':
                            total_repaid += float(amount)
                    except (ValueError, TypeError):
                        continue

            credit_status = {
                "total_loaned": total_loaned,
                "total_repaid": total_repaid,
                "credit_limit": total_repaid * 2.5,
                "total_income_interest": total_repaid - total_loaned,
                "last_contract": str(latest_date) if latest_date else None
            }

            return credit_status

        except Exception as e:
            logger.error(f"Error in account_status: {e}")
            return {
                "total_loaned": 0,
                "total_repaid": 0,
                "credit_limit": 0,
                "total_income_interest": 0,
                "last_contract": None
            }

    def recent_borrower_history(self, borrower_id):
        """Returns a list of dictionaries representing the borrower's 3 most recent loans."""
        try:
            if not borrower_id:
                return []

            response = (
                self.supabase
                .table('loans')
                .select('*')
                .eq('borrower_id', borrower_id)
                .order('created_at', desc=True)
                .limit(3)
                .execute()
            )

            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error in recent_borrower_history: {response.error}")
                return []

            raw_data = response.data or []

            if not raw_data:
                return []

            recent_history = []

            for data in raw_data:
                try:
                    # Fetch and sum repayment amounts
                    repayment_response = (
                        self.supabase
                        .table('repayments')
                        .select('amount')
                        .eq('loan_id', data.get('id'))
                        .execute()
                    )

                    repaid_amount = 0
                    if not (hasattr(repayment_response, 'error') and repayment_response.error):
                        repayment_data = repayment_response.data or []
                        for item in repayment_data:
                            try:
                                amount = item.get('amount')
                                if amount is not None:
                                    repaid_amount += float(amount)
                            except (ValueError, TypeError):
                                continue

                    # Handle date conversion
                    created_at_date = None
                    if data.get('created_at'):
                        try:
                            created_at_date = datetime.fromisoformat(data['created_at']).date()
                        except (ValueError, TypeError):
                            created_at_date = None

                    # Get loan amount and interest rate safely
                    loan_amount = 0
                    try:
                        loan_amount = float(data.get('amount', 0))
                    except (ValueError, TypeError):
                        pass

                    interest_rate = 0
                    try:
                        interest_rate = float(data.get('interest_rate', 0))
                    except (ValueError, TypeError):
                        pass

                    # Calculate balance
                    total_due = loan_amount + (loan_amount * interest_rate / 100)
                    balance = round(total_due - repaid_amount, 2)

                    # Handle due date
                    end_date = None
                    if data.get('due_date'):
                        try:
                            end_date = data['due_date'][:10] if len(data['due_date']) >= 10 else data['due_date']
                        except (TypeError, AttributeError):
                            end_date = None

                    loan_info = {
                        'start_date': str(created_at_date) if created_at_date else None,
                        'amount': loan_amount,
                        'interest_rate': f"{interest_rate}%",
                        'end_date': end_date,
                        'status': data.get('status', 'Unknown'),
                        'repaid_amount': repaid_amount,
                        'balance': balance
                    }

                    recent_history.append(loan_info)

                except Exception as e:
                    logger.error(f"Error processing loan data: {e}")
                    continue

            return recent_history

        except Exception as e:
            logger.error(f"Error in recent_borrower_history: {e}")
            return []

    def get_borrowers(self):
        """Returns a list of borrowers from the database."""

        try:
            response = (
                self.supabase
                .table('borrowers')
                .select('*')
                .execute()
            )

            borrowers = response.data if response.data else []
            return borrowers

        except Exception as e:
            print(f'Exception: {e}')
            return []
