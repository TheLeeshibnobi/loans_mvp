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
        # Cash in
        injection_response = (
            self.supabase
            .table('injections')
            .select('amount')
            .execute()
        )
        injection_total = sum(item['amount'] for item in injection_response.data)

        # Cash out
        disbursements_response = (
            self.supabase
            .table('disbursements')
            .select('amount')
            .execute()
        )
        disbursements_total = sum(item['amount'] for item in disbursements_response.data)

        # Ensure net equity is never negative
        return max(injection_total - disbursements_total, 0)

    def net_loans(self):
        """Gets the net of disbursed loans and repaid loans using the cashflow table."""
        # loan repayments
        repayments_response = (
            self.supabase
            .table('repayments')
            .select('amount')
            .execute()
        )

        repayments_total = sum(item['amount'] for item in repayments_response.data)


        # loans given out
        loans_response = (
            self.supabase
            .table('loans')
            .select('amount')
            .execute()
        )

        loans_total = sum(item['amount'] for item in loans_response.data)

        return repayments_total - loans_total



    def available_cash(self):
        """returns the total available cash in the system bu adding the net equity and net loans"""
        available_cash = self.net_equity() + self.net_loans()
        return round(available_cash, 2)

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
        period, today = self.get_period(days)

        # Query the loans table instead of disbursements table
        response = (
            self.supabase.table('loans')
            .select('amount')
            .gte('created_at', period.isoformat())
            .lte('created_at', today.isoformat())
            .execute()
        )

        if response.data:
            total_amount = sum(row['amount'] for row in response.data)
            return round(total_amount, 2)
        return 0

    def total_repaid(self, days):
        """returns the total amount repaid"""
        period, today = self.get_period(days)

        response = (
            self.supabase.table('repayments')
            .select('amount')
            .gte('created_at', period)  # corrected column name
            .lte('created_at', today)
            .execute()
        )

        if response.data:
            total_amount = sum(row['amount'] for row in response.data)
            return round(total_amount, 2)
        return 0

    def outstanding_balance(self, days):
        """returns the outstanding balance not yet paid"""
        period, today = self.get_period(days)
        period = period.isoformat()
        today = today.isoformat()

        response = (
            self.supabase.table('loans')
            .select('amount')
            .neq('status', 'Completed')
            .gte('created_at', period)  # corrected column name
            .lte('created_at', today)
            .execute()
        )

        if response.data:
            total_amount = sum(row['amount'] for row in response.data)
            return round(total_amount, 2)
        return 0

    def expected_interest(self, days):
        """Returns the total expected interest."""
        period, today = self.get_period(days)
        period = period.isoformat()
        today = today.isoformat()

        response = (
            self.supabase.table('loans')
            .select('amount, interest_rate')
            .gte('created_at', period)  # corrected column name
            .lte('created_at', today)
            .execute()
        )

        if response.data:
            total_interest = sum(
                row['amount'] * row['interest_rate'] / 100 for row in response.data
            )
            return round(total_interest, 2)
        return 0

    def average_loan_size(self, days):
        """Returns the average loan size for a certain period."""
        period, today = self.get_period(days)

        response = (
            self.supabase.table('loans')
            .select('amount')
            .gte('created_at', period.isoformat())
            .lte('created_at', today.isoformat())
            .execute()
        )

        if response.data:
            total_amount = sum(row['amount'] for row in response.data)
            average = total_amount / len(response.data)
            return round(average, 2)
        return 0

    def average_duration(self, days):
        """returns the average loan duration for a certain period"""
        period, today = self.get_period(days)

        response = (
            self.supabase.table('loans')
            .select('duration_days')
            .gte('created_at', period.isoformat())
            .lte('created_at', today.isoformat())
            .execute()
        )

        if response.data:
            total_days = sum(row['duration_days'] for row in response.data)
            average = total_days / len(response.data)
            return round(average, 0)  # Round to whole days
        return 0

    def active_loans(self, days):
        """returns the number of active loans"""
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

    def default_rate(self, days):
        """Returns the default rate of loans during a given period."""
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

    def total_transaction_costs(self, days):
        """Returns the total transaction cost for the specified period."""
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
        total_transaction_cost = sum(item['transaction_costs'] or 0 for item in response.data)

        return round(total_transaction_cost, 2)

    def total_discounts_given(self, days):
        """Returns the total discount given for the specified period."""
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
        total_discount_cost = sum(item['discount'] or 0 for item in response.data)

        return round(total_discount_cost, 2)

    def recent_borrowers(self):
        """Returns a dictionary of 4 recent borrowers"""
        response = (
            self.supabase
            .table('loans')
            .select('borrower_id', 'amount', 'status', 'file_url', 'collateral_photos')
            .order('id', desc=True)
            .limit(4)
            .execute()
        )

        recent_borrowers = []
        for data in response.data:
            borrower_info = (
                self.supabase
                .table('borrowers')
                .select('name')
                .eq('id', data['borrower_id'])
                .execute()
            ).data

            borrower_name = borrower_info[0]['name'] if borrower_info else "Unknown"

            # Ensure collateral_photos is a list, default to empty list if None or invalid
            collateral_photos = data.get('collateral_photos', []) if isinstance(data.get('collateral_photos'),
                                                                                list) else []

            recent_borrowers.append({
                'name': borrower_name,
                'amount': f"ZMK {data['amount']:,.2f}",  # Format amount here
                'status': data['status'],
                'contract': data['file_url'],
                'collateral_photos': collateral_photos
            })

        return recent_borrowers

    def locations_ids(self, days):
        """returns a dictionary of locations and the borrowers ids that belong to that location"""
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

        # Step 2: Get unique locations
        unique_locations = list(dict.fromkeys(item['location'] for item in current_cities.data))

        # Step 3: Map each location to its borrower IDs within the same date range
        locations_borrowers_ids = {}
        for city in unique_locations:
            id_info = (
                self.supabase
                .table('borrowers')
                .select('id')
                .eq('location', city)
                .gt('created_at', start_date)
                .lt('created_at', end_date)
                .execute()
            )
            ids = [item['id'] for item in id_info.data]
            locations_borrowers_ids[city] = ids

        return locations_borrowers_ids

    def location_totals(self, days):
        """Returns a dictionary of total loan amounts given to each location."""
        location_ids = self.locations_ids(days)
        location_totals = {}

        for location, id_list in location_ids.items():
            total = 0
            for borrower_id in id_list:
                response = (
                    self.supabase
                    .table('loans')
                    .select('amount')
                    .eq('borrower_id', borrower_id)
                    .execute()
                )
                # Sum all amounts in this borrower's loans
                total += sum(item['amount'] for item in response.data if 'amount' in item)

            location_totals[location] = round(total, 2)

        return location_totals

    def location_loan_numbers(self, days):
        """returns a dictionary of the total number of loans in the specific location"""
        location_ids = self.locations_ids(days)
        location_loan_number = {}

        for location, id_list in location_ids.items():
            location_loan_number[location] = len(id_list)
        return location_loan_number

    def location_average_loan(self, days):
        """Returns a dictionary of average loan amounts per location."""
        location_totals = self.location_totals(days)
        location_loan_numbers = self.location_loan_numbers(days)

        location_averages = {}
        for location in location_totals:
            total = location_totals[location]
            num_loans = location_loan_numbers.get(location, 0)
            average = total / num_loans if num_loans > 0 else 0
            location_averages[location] = round(average, 2)

        return location_averages

    def borrowers_by_location(self, days):
        """Creates a dictionary summary of total borrowers, loans, and average loan per location."""

        # Get data from existing methods
        location_ids = self.locations_ids(days)
        location_totals = self.location_totals(days)
        location_averages = self.location_average_loan(days)

        summary = {}
        for location in location_ids:
            summary[location] = {
                "total_borrowers": len(location_ids[location]),
                "total_loans": f"{location_totals.get(location, 0):,.2f}",  # Format with commas
                "average_loan": f"{location_averages.get(location, 0):,.2f}"  # Format with commas
            }

        return summary

    def weekly_loans_due(self):
        """returns a list of loans that are due in the upcoming 7 days"""
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

        # create the due dates list

        weekly_loans_due = []
        for info in response.data:
            borrower_id = info["borrower_id"]
            # get the name of that id from the borrowers table
            borrower_info = self.supabase.table('borrowers').select('name').eq('id', borrower_id).execute().data
            borrower_name = borrower_info[0]['name'] if borrower_info else "Unknown"
            due_date = info["due_date"]
            amount = info["amount"] + (info["amount"] * (info["interest_rate"] / 100))
            loan_data = {
                'name': borrower_name,
                'due_date': due_date,
                'amount': round(amount, 2)  # Round the amount
            }
            weekly_loans_due.append(loan_data)

        return weekly_loans_due


