from supabase import create_client, Client
from datetime import date, timedelta, datetime, UTC
from dotenv import load_dotenv
import os


class OverviewMetrics:
    """Contains metrics for the overview dashboard"""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

    def net_equity(self):
        """Gets the net of equity inserted and dividends paid out — never returns a negative value."""
        try:
            # Cash in
            injection_response = (
                self.supabase
                .table('injections')
                .select('amount')
                .execute()
            )
            injection_total = sum(item['amount'] for item in (injection_response.data or []))

            # Cash out
            disbursements_response = (
                self.supabase
                .table('disbursements')
                .select('amount')
                .execute()
            )
            disbursements_total = sum(item['amount'] for item in (disbursements_response.data or []))

            # Ensure net equity is never negative
            return max(injection_total - disbursements_total, 0)
        except Exception as e:
            print(f"Error calculating net equity: {e}")
            return 0

    def net_loans(self):
        """Gets the net of disbursed loans and repaid loans using the cashflow table."""
        try:
            # loan repayments
            repayments_response = (
                self.supabase
                .table('repayments')
                .select('amount')
                .execute()
            )

            repayments_total = sum(item['amount'] for item in (repayments_response.data or []))

            # loans given out
            loans_response = (
                self.supabase
                .table('loans')
                .select('amount')
                .execute()
            )

            loans_total = sum(item['amount'] for item in (loans_response.data or []))

            return repayments_total - loans_total
        except Exception as e:
            print(f"Error calculating net loans: {e}")
            return 0

    def total_money_in(self):
        """Returns the total of capital in plus loan repayment amount."""
        repayments_response = self.supabase.table('repayments').select('amount').execute()
        injections_response = self.supabase.table('injections').select('amount').execute()

        repayments_total = sum(item['amount'] for item in repayments_response.data)
        injections_total = sum(item['amount'] for item in injections_response.data)

        return repayments_total + injections_total

    def total_money_out(self):
        """Returns the total of money disbursed and loans given out."""
        disbursements_response = self.supabase.table('disbursements').select('amount').execute()
        loans_response = self.supabase.table('loans').select('amount').execute()

        disbursements_total = sum(item['amount'] for item in disbursements_response.data)
        loans_total = sum(item['amount'] for item in loans_response.data)

        return disbursements_total + loans_total

    def available_cash(self):
        """returns the total available cash in the system but adding the net equity and net loans"""
        available_cash = self.total_money_in() - self.total_money_out()
        return available_cash

    def get_period(self, days):
        """Fixed to handle both string and numeric period inputs"""
        today = datetime.now(UTC)

        # Handle string inputs from dropdown
        if days == 'Last 7 Days' or days == '7':
            period = today - timedelta(days=7)
        elif days == 'Last 30 Days' or days == '30':
            period = today - timedelta(days=30)
        elif days == 'Last 3 Months' or days == '90':
            period = today - timedelta(days=90)
        elif days == 'Last 6 Months' or days == '180':
            period = today - timedelta(days=180)
        elif days == 'Last 12 Months' or days == '365':
            period = today - timedelta(days=365)
        elif days == 'This Month' or days == 'current_month':
            period = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif days == 'This Year' or days == 'current_year':
            period = today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            # Default to last 30 days
            period = today - timedelta(days=30)
        return period, today

    def total_disbursed(self, days):
        """Returns the total disbursed amount of loans - FIXED to use loans table"""
        try:
            period, today = self.get_period(days)

            # Query the loans table instead of disbursements table
            response = (
                self.supabase.table('loans')
                .select('amount')
                .gte('created_at', period.isoformat())
                .lte('created_at', today.isoformat())
                .execute()
            )

            if response.data and len(response.data) > 0:
                total_amount = sum(row['amount'] for row in response.data)
                return round(total_amount, 2)
            return 0
        except Exception as e:
            print(f"Error calculating total disbursed: {e}")
            return 0

    def total_repaid(self, days):
        """returns the total amount repaid"""
        try:
            period, today = self.get_period(days)

            response = (
                self.supabase.table('repayments')
                .select('amount')
                .gte('created_at', period.isoformat())
                .lte('created_at', today.isoformat())
                .execute()
            )

            if response.data and len(response.data) > 0:
                total_amount = sum(row['amount'] for row in response.data)
                return round(total_amount, 2)
            return 0
        except Exception as e:
            print(f"Error calculating total repaid: {e}")
            return 0

    def outstanding_balance(self, days):
        """returns the outstanding balance not yet paid"""
        try:
            period, today = self.get_period(days)
            period = period.isoformat()
            today = today.isoformat()

            response = (
                self.supabase.table('loans')
                .select('amount')
                .neq('status', 'Completed')
                .gte('created_at', period)
                .lte('created_at', today)
                .execute()
            )

            if response.data and len(response.data) > 0:
                total_amount = sum(row['amount'] for row in response.data)
                return round(total_amount, 2)
            return 0
        except Exception as e:
            print(f"Error calculating outstanding balance: {e}")
            return 0

    def expected_interest(self, days):
        """Returns the total expected interest."""
        try:
            period, today = self.get_period(days)
            period = period.isoformat()
            today = today.isoformat()

            response = (
                self.supabase.table('loans')
                .select('amount, interest_rate')
                .gte('created_at', period)
                .lte('created_at', today)
                .eq('status', 'Active')
                .execute()
            )

            if response.data and len(response.data) > 0:
                total_interest = sum(
                    row['amount'] * row['interest_rate'] / 100 for row in response.data
                )
                return round(total_interest, 2)
            return 0
        except Exception as e:
            print(f"Error calculating expected interest: {e}")
            return 0

    def average_loan_size(self, days):
        """Returns the average loan size for a certain period."""
        try:
            period, today = self.get_period(days)

            response = (
                self.supabase.table('loans')
                .select('amount')
                .gte('created_at', period.isoformat())
                .lte('created_at', today.isoformat())
                .execute()
            )

            if response.data and len(response.data) > 0:
                total_amount = sum(row['amount'] for row in response.data)
                average = total_amount / len(response.data)
                return round(average, 2)
            return 0
        except Exception as e:
            print(f"Error calculating average loan size: {e}")
            return 0

    def average_duration(self, days):
        """returns the average loan duration for a certain period"""
        try:
            period, today = self.get_period(days)

            response = (
                self.supabase.table('loans')
                .select('duration_days')
                .gte('created_at', period.isoformat())
                .lte('created_at', today.isoformat())
                .execute()
            )

            if response.data and len(response.data) > 0:
                total_days = sum(row['duration_days'] for row in response.data)
                average = total_days / len(response.data)
                return round(average, 0)  # Round to whole days
            return 0
        except Exception as e:
            print(f"Error calculating average duration: {e}")
            return 0

    def active_loans(self, days):
        """returns the number of active loans"""
        try:
            period, today = self.get_period(days)

            response = (
                self.supabase.table('loans')
                .select('status')
                .eq('status', 'Active')
                .gte('created_at', period.isoformat())
                .lte('created_at', today.isoformat())
                .execute()
            )

            if response.data:
                return len(response.data)
            else:
                return 0
        except Exception as e:
            print(f"Error calculating active loans: {e}")
            return 0

    def default_rate(self, days):
        """Returns the default rate of loans during a given period."""
        try:
            period, today = self.get_period(days)
            start_date = period.isoformat()
            end_date = today.isoformat()

            # Fetch total loans during the period
            total_response = (
                self.supabase.table('loans')
                .select('id')  # Only select what's needed
                .gte('created_at', start_date)
                .lte('created_at', end_date)
                .execute()
            )

            total_loans = total_response.data or []
            total_count = len(total_loans)

            if total_count == 0:
                return 0  # Avoid division by zero

            # Fetch defaulted (e.g. "Overdue") loans during the period
            default_response = (
                self.supabase.table('loans')
                .select('id')  # Again, only select what's needed
                .eq('status', 'Overdue')
                .gte('created_at', start_date)
                .lte('created_at', end_date)
                .execute()
            )

            defaulted_loans = default_response.data or []
            default_count = len(defaulted_loans)

            return round((default_count / total_count) * 100, 1)  # Round to 1 decimal place
        except Exception as e:
            print(f"Error calculating default rate: {e}")
            return 0

    def total_transaction_costs(self, days):
        """Returns the total transaction cost for the specified period."""
        try:
            period, today = self.get_period(days)
            start_date = period.isoformat()
            end_date = today.isoformat()

            # Fetch transaction costs during the period
            response = (
                self.supabase.table('loans')
                .select('transaction_costs')  # Only select what's needed
                .gte('created_at', start_date)
                .lte('created_at', end_date)
                .execute()
            )

            # Sum transaction costs, treating None as 0
            if response.data and len(response.data) > 0:
                total_transaction_cost = sum(item['transaction_costs'] or 0 for item in response.data)
                return round(total_transaction_cost, 2)
            return 0
        except Exception as e:
            print(f"Error calculating total transaction costs: {e}")
            return 0

    def total_discounts_given(self, days):
        """Returns the total discount given for the specified period."""
        try:
            period, today = self.get_period(days)
            start_date = period.isoformat()
            end_date = today.isoformat()

            # Fetch total loans during the period
            response = (
                self.supabase.table('repayments')
                .select('discount')
                .gte('created_at', start_date)
                .lte('created_at', end_date)
                .execute()
            )

            # Safely sum discounts, treating None as 0
            if response.data and len(response.data) > 0:
                total_discount_cost = sum(item['discount'] or 0 for item in response.data)
                return round(total_discount_cost, 2)
            return 0
        except Exception as e:
            print(f"Error calculating total discounts given: {e}")
            return 0

    def recent_borrowers(self):
        """Returns a dictionary of 4 recent borrowers including NRC number, issue date, and due date"""
        try:
            response = (
                self.supabase
                .table('loans')
                .select('id', 'borrower_id', 'amount', 'status', 'created_at', 'due_date')
                .order('id', desc=True)
                .limit(4)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                return []

            recent_borrowers = []
            for loan in response.data:
                try:
                    # Step 1: Get borrower name and NRC number
                    borrower_info = (
                        self.supabase
                        .table('borrowers')
                        .select('name', 'nrc_number')
                        .eq('id', loan['borrower_id'])
                        .execute()
                    ).data

                    if borrower_info:
                        borrower_name = borrower_info[0]['name']
                        nrc_number = borrower_info[0]['nrc_number']
                    else:
                        borrower_name = "Unknown"
                        nrc_number = "N/A"

                    # Step 2: Get files for the loan
                    file_info = (
                        self.supabase
                        .table('files')
                        .select('docs', 'photos')
                        .eq('loan_id', loan['id'])
                        .limit(1)
                        .execute()
                    ).data
                    file_data = file_info[0] if file_info else {}

                    # FIX: Extract the first contract URL from the docs array
                    docs_array = file_data.get('docs', [])
                    contract = docs_array[0] if docs_array and len(docs_array) > 0 else None

                    collateral_photos = file_data.get('photos', []) if isinstance(file_data.get('photos'), list) else []

                    recent_borrowers.append({
                        'name': borrower_name,
                        'nrc_number': nrc_number,
                        'amount': f"ZMK {loan['amount']:,.2f}",
                        'status': loan['status'],
                        'issue_date': loan['created_at'],
                        'due_date': loan['due_date'],
                        'contract': contract,
                        'collateral_photos': collateral_photos
                    })
                except Exception as e:
                    print(f"Error processing borrower data: {e}")
                    continue

            return recent_borrowers
        except Exception as e:
            print(f"Error getting recent borrowers: {e}")
            return []

    def locations_ids(self, days):
        """returns a dictionary of locations and the borrowers ids that belong to that location"""
        try:
            period, today = self.get_period(days)
            start_date = period.isoformat()
            end_date = today.isoformat()

            # Step 1: Get location data within date range
            current_cities = (
                self.supabase
                .table('borrowers')
                .select('location')
                .gt('created_at', start_date)
                .lt('created_at', end_date)
                .execute()
            )

            if not current_cities.data or len(current_cities.data) == 0:
                return {}

            # Step 2: Get unique locations
            unique_locations = list(dict.fromkeys(item['location'] for item in current_cities.data if item.get('location')))

            # Step 3: Map each location to its borrower IDs within the same date range
            locations_borrowers_ids = {}
            for city in unique_locations:
                try:
                    id_info = (
                        self.supabase
                        .table('borrowers')
                        .select('id')
                        .eq('location', city)
                        .gt('created_at', start_date)
                        .lt('created_at', end_date)
                        .execute()
                    )
                    ids = [item['id'] for item in (id_info.data or [])]
                    locations_borrowers_ids[city] = ids
                except Exception as e:
                    print(f"Error processing location {city}: {e}")
                    locations_borrowers_ids[city] = []

            return locations_borrowers_ids
        except Exception as e:
            print(f"Error getting locations IDs: {e}")
            return {}

    def location_totals(self, days):
        """Returns a dictionary of total loan amounts given to each location."""
        try:
            location_ids = self.locations_ids(days)
            if not location_ids:
                return {}

            location_totals = {}

            for location, id_list in location_ids.items():
                total = 0
                for borrower_id in id_list:
                    try:
                        response = (
                            self.supabase
                            .table('loans')
                            .select('amount')
                            .eq('borrower_id', borrower_id)
                            .execute()
                        )
                        # Sum all amounts in this borrower's loans
                        if response.data and len(response.data) > 0:
                            total += sum(item['amount'] for item in response.data if 'amount' in item)
                    except Exception as e:
                        print(f"Error processing borrower {borrower_id}: {e}")
                        continue

                location_totals[location] = round(total, 2)

            return location_totals
        except Exception as e:
            print(f"Error calculating location totals: {e}")
            return {}

    def location_loan_numbers(self, days):
        """returns a dictionary of the total number of loans in the specific location"""
        try:
            location_ids = self.locations_ids(days)
            if not location_ids:
                return {}

            location_loan_number = {}

            for location, id_list in location_ids.items():
                location_loan_number[location] = len(id_list)
            return location_loan_number
        except Exception as e:
            print(f"Error calculating location loan numbers: {e}")
            return {}

    def location_average_loan(self, days):
        """Returns a dictionary of average loan amounts per location."""
        try:
            location_totals = self.location_totals(days)
            location_loan_numbers = self.location_loan_numbers(days)

            if not location_totals or not location_loan_numbers:
                return {}

            location_averages = {}
            for location in location_totals:
                total = location_totals[location]
                num_loans = location_loan_numbers.get(location, 0)
                average = total / num_loans if num_loans > 0 else 0
                location_averages[location] = round(average, 2)

            return location_averages
        except Exception as e:
            print(f"Error calculating location average loans: {e}")
            return {}

    def borrowers_by_location(self, days):
        """Creates a dictionary summary of total borrowers, loans, and average loan per location."""
        try:
            # Get data from existing methods
            location_ids = self.locations_ids(days)
            location_totals = self.location_totals(days)
            location_averages = self.location_average_loan(days)

            if not location_ids:
                return {}

            summary = {}
            for location in location_ids:
                summary[location] = {
                    "total_borrowers": len(location_ids[location]),
                    "total_loans": f"{location_totals.get(location, 0):,.2f}",  # Format with commas
                    "average_loan": f"{location_averages.get(location, 0):,.2f}"  # Format with commas
                }

            return summary
        except Exception as e:
            print(f"Error calculating borrowers by location: {e}")
            return {}

    def weekly_loans_due(self):
        """returns a list of loans that are due in the upcoming 7 days"""
        try:
            today = datetime.today().date()
            next_week = today + timedelta(days=7)

            start_date = today.isoformat()
            end_date = next_week.isoformat()

            print(f"Looking for due dates between {start_date} and {end_date}")

            response = (
                self.supabase
                .table('loans')
                .select('borrower_id', 'amount', 'interest_rate', 'due_date')
                .gt('due_date', start_date)
                .lt('due_date', end_date)
                .neq('status', 'Completed')
                .execute()
            )

            if not response.data or len(response.data) == 0:
                return []

            # create the due dates list
            weekly_loans_due = []
            for info in response.data:
                try:
                    borrower_id = info["borrower_id"]
                    # get the name of that id from the borrowers table
                    borrower_info = self.supabase.table('borrowers').select('name').eq('id', borrower_id).execute().data
                    borrower_name = borrower_info[0]['name'] if borrower_info and len(borrower_info) > 0 else "Unknown"
                    due_date = info["due_date"]
                    amount = info["amount"] + (info["amount"] * (info["interest_rate"] / 100))
                    loan_data = {
                        'name': borrower_name,
                        'due_date': due_date,
                        'amount': round(amount, 2)  # Round the amount
                    }
                    weekly_loans_due.append(loan_data)
                except Exception as e:
                    print(f"Error processing loan due data: {e}")
                    continue

            return weekly_loans_due
        except Exception as e:
            print(f"Error getting weekly loans due: {e}")
            return []

test = OverviewMetrics()
print(
    test.available_cash()
)